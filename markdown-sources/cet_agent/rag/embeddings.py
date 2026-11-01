"""The only file that talks to Ollama for vectors.

Chunks and questions must be embedded with the SAME model, so both go through here.
"""
import ollama

from config import EMBED_BATCH_SIZE, EMBEDDING_MODEL, QUERY_PREFIX


def _embed(batch):
    """One Ollama call. Returns one vector per input string, in the same order."""
    try:
        return ollama.embed(model=EMBEDDING_MODEL, input=batch)["embeddings"]
    except ConnectionError as e:
        raise RuntimeError("Cannot reach Ollama. Is it running? Try: ollama serve") from e
    except ollama.ResponseError as e:
        if e.status_code == 404:
            raise RuntimeError(f"Model not found in Ollama. Run: ollama pull {EMBEDDING_MODEL}") from e
        raise


def embed_texts(texts, batch_size=EMBED_BATCH_SIZE):
    """Embed many strings (used for chunks). Output order matches input order."""
    if any(not t.strip() for t in texts):
        raise ValueError("embed_texts got an empty string; filter empties before embedding")
    vectors = []
    for start in range(0, len(texts), batch_size):
        vectors.extend(_embed(texts[start:start + batch_size]))
    return vectors


def embed_query(question):
    """Embed one search question (used by the retriever). Adds the query prefix."""
    return _embed([QUERY_PREFIX + question])[0]


if __name__ == "__main__":
    vecs = embed_texts(["Cats sleep a lot.", "The engine needs an oil change."])
    print("vectors:", len(vecs), "dimension:", len(vecs[0]))
