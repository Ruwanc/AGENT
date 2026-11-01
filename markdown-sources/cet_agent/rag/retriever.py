"""Search the vector store with a question."""
from config import TOP_K
from config import MAX_CONTEXT_CHARS
from cet_agent.rag.store import get_collection, get_section, query


def search(question, k=TOP_K, source=None, collection=None, embed_fn=None):
    """Return the k most similar chunks (dicts with text, similarity, note_path, ...).

    source="company" limits the search to one folder from config.SOURCES.
    """
    if embed_fn is None:
        from cet_agent.rag.embeddings import embed_query as embed_fn
    collection = collection or get_collection()
    where = {"source": source} if source else None
    return query(collection, embed_fn(question), k=k, where=where)


def expand_sections(hits, collection=None, max_chars=MAX_CONTEXT_CHARS):
    """Add the sibling chunks of each matched section, so the model sees the whole section.

    Example: a big table is stored as 3 chunks. Search matches only piece 2, but the
    answer is in piece 1. Expanding gives the model all 3 pieces, in order.
    The original hits are always kept; siblings are added only while the total
    text stays under max_chars. Siblings get the similarity of the hit that pulled them in.
    """
    collection = collection or get_collection()
    out, seen_ids, seen_sections = [], set(), set()
    total = sum(len(h["text"]) for h in hits)
    for hit in hits:
        key = (hit["source"], hit["note_path"], hit["heading_path"])
        if key in seen_sections:
            continue
        seen_sections.add(key)
        for chunk in get_section(collection, *key) or [hit]:
            if chunk["id"] in seen_ids:
                continue
            is_hit = chunk["id"] in {h["id"] for h in hits}
            if not is_hit:
                if total + len(chunk["text"]) > max_chars:
                    continue
                total += len(chunk["text"])
            seen_ids.add(chunk["id"])
            match = next((h for h in hits if h["id"] == chunk["id"]), None)
            out.append(match or {**chunk, "similarity": hit["similarity"],
                                 "distance": hit["distance"], "expanded": True})
    # hits from sections already handled above may still be missing (different section order)
    out += [h for h in hits if h["id"] not in seen_ids]
    return out
