"""The only file that talks to ChromaDB.

One collection holds every chunk from every source. Each record has:
    id         "docs:guides/install.md::1"          (from sources.chunk_id)
    embedding  768 numbers from the embedding model
    document   the chunk text ("Title > Heading\\n\\npiece")
    metadata   source, note_path, title, heading_path, chunk_index, tags, hash
"""
import chromadb

from config import CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL

UPSERT_BATCH = 500          # Chroma limits how many records one call can take


def get_collection(path=CHROMA_DIR, name=COLLECTION_NAME, embedding_model=EMBEDDING_MODEL):
    """Open (or create) the collection on disk, using cosine distance.

    The embedding model's name is saved with the collection. Vectors from two
    different models can't be compared, so opening it with another model fails
    with a clear message instead of returning nonsense results.
    """
    client = chromadb.PersistentClient(path=str(path))
    collection = client.get_or_create_collection(
        name=name,
        metadata={"hnsw:space": "cosine", "embedding_model": embedding_model},
        embedding_function=None,            # we always pass our own vectors
    )
    saved = (collection.metadata or {}).get("embedding_model")
    if saved and saved != embedding_model:
        raise RuntimeError(
            f"Collection '{name}' was built with '{saved}' but config uses '{embedding_model}'. "
            "Run `python -m scripts.index --reset` to rebuild it."
        )
    return collection


def reset_collection(path=CHROMA_DIR, name=COLLECTION_NAME):
    """Delete the whole collection (all chunks). The next index run rebuilds it."""
    client = chromadb.PersistentClient(path=str(path))
    try:
        client.delete_collection(name)
    except Exception:          # it did not exist: nothing to delete
        pass


def upsert_chunks(collection, ids, texts, embeddings, metadatas):
    """Insert or replace records. Same id = replace, so re-running is safe."""
    for start in range(0, len(ids), UPSERT_BATCH):
        end = start + UPSERT_BATCH
        collection.upsert(ids=ids[start:end], documents=texts[start:end],
                          embeddings=embeddings[start:end], metadatas=metadatas[start:end])


def delete_document(collection, source, note_path):
    """Remove every chunk of one file (used when a file changes or is deleted)."""
    collection.delete(where={"$and": [{"source": source}, {"note_path": note_path}]})


def stored_hashes(collection, page=1000):
    """{(source, note_path): hash} for every file already in the collection."""
    found, offset = {}, 0
    while True:
        batch = collection.get(include=["metadatas"], limit=page, offset=offset)["metadatas"]
        if not batch:
            return found
        for m in batch:
            found[(m["source"], m["note_path"])] = m["hash"]
        offset += page


def query(collection, embedding, k=5, where=None):
    """Top-k chunks for one query vector, as plain dicts, best first.

    With cosine space, distance 0 = same direction; similarity = 1 - distance.
    """
    if collection.count() == 0:
        return []
    res = collection.query(query_embeddings=[embedding], n_results=min(k, collection.count()),
                           where=where, include=["documents", "metadatas", "distances"])
    return [
        {"id": i, "text": doc, "distance": dist, "similarity": 1 - dist, **meta}
        for i, doc, meta, dist in zip(res["ids"][0], res["documents"][0],
                                      res["metadatas"][0], res["distances"][0])
    ]


def get_section(collection, source, note_path, heading_path):
    """All chunks of one section (same file + heading path), in document order."""
    res = collection.get(
        where={"$and": [{"source": source}, {"note_path": note_path}, {"heading_path": heading_path}]},
        include=["documents", "metadatas"],
    )
    rows = [{"id": i, "text": doc, **meta}
            for i, doc, meta in zip(res["ids"], res["documents"], res["metadatas"])]
    return sorted(rows, key=lambda r: r["chunk_index"])
