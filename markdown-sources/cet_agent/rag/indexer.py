"""Keep ChromaDB in sync with the Markdown folders.

Each file's SHA-256 hash is stored in its chunks' metadata, so no separate
manifest file is needed:

    new file          -> chunk, embed, add
    changed file      -> delete its old chunks, then chunk, embed, add
    unchanged file    -> skip (no Ollama call)
    deleted file      -> delete its chunks
    missing folder    -> skipped, and its chunks are KEPT (a disconnected drive
                         should not wipe your index)
"""
from config import SOURCES
from cet_agent.rag.chunking import chunk_note
from cet_agent.rag.sources import chunk_id, chunk_metadata, load_source
from cet_agent.rag.store import delete_document, get_collection, stored_hashes, upsert_chunks


def index_document(collection, doc, embed_fn):
    """Replace all chunks of one document. Returns how many chunks were written."""
    delete_document(collection, doc["source"], doc["path"])
    chunks = chunk_note(doc)
    if not chunks:
        return 0
    texts = [c["text"] for c in chunks]
    upsert_chunks(
        collection,
        ids=[chunk_id(c, doc["source"]) for c in chunks],
        texts=texts,
        embeddings=embed_fn(texts),
        metadatas=[chunk_metadata(doc, c) for c in chunks],
    )
    return len(chunks)


def sync(sources=SOURCES, collection=None, embed_fn=None, force=False, log=print):
    """Bring the collection up to date with the folders. Returns a stats dict.

    force=True re-embeds every file even if its hash is unchanged.
    embed_fn can be replaced in tests so they run without Ollama.
    """
    if embed_fn is None:
        from cet_agent.rag.embeddings import embed_texts as embed_fn
    collection = collection or get_collection()
    existing = stored_hashes(collection)
    stats = {"added": 0, "updated": 0, "unchanged": 0, "deleted": 0, "chunks_written": 0}

    for source in sources:
        try:
            docs = list(load_source(source))
        except FileNotFoundError as e:
            log(f"[skip] {e}  (its chunks are kept)")
            continue

        seen = set()
        for doc in docs:
            key = (doc["source"], doc["path"])
            seen.add(key)
            old_hash = existing.get(key)
            if old_hash == doc["hash"] and not force:
                stats["unchanged"] += 1
                continue
            n = index_document(collection, doc, embed_fn)
            stats["chunks_written"] += n
            stats["updated" if old_hash else "added"] += 1
            log(f"[{'update' if old_hash else 'add'}] {key[0]}:{key[1]}  ({n} chunks)")

        for key in existing:
            if key[0] == source["name"] and key not in seen:
                delete_document(collection, *key)
                stats["deleted"] += 1
                log(f"[delete] {key[0]}:{key[1]}")

    stats["total_chunks"] = collection.count()
    return stats
