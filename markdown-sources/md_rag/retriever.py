"""Search the vector store with a question."""
from config import TOP_K
from md_rag.store import get_collection, query


def search(question, k=TOP_K, source=None, collection=None, embed_fn=None):
    """Return the k most similar chunks (dicts with text, similarity, note_path, ...).

    source="docs" limits the search to one folder from config.SOURCES.
    """
    if embed_fn is None:
        from md_rag.embeddings import embed_query as embed_fn
    collection = collection or get_collection()
    where = {"source": source} if source else None
    return query(collection, embed_fn(question), k=k, where=where)
