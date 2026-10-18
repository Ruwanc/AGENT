"""Scratch check: chunking.py -> embeddings.py, then a tiny in-memory search.

Run from the project root:  python scripts_try_chunks_and_embeddings.py
(The real pipeline will store the vectors in ChromaDB instead of a list.)
"""
from rag.chunking import chunk_note
from rag.embeddings import embed_query, embed_texts

note = {
    "path": "Pets/Cats.md",
    "title": "Cats",
    "tags": ["pets"],
    "body": (
        "# Cats\n"
        "Cats are popular pets found all around the world.\n\n"
        "## Sleep\n"
        "Cats sleep between 12 and 16 hours per day, and kittens sleep even more.\n\n"
        "## Diet\n"
        "Cats are obligate carnivores and need meat to stay healthy.\n\n"
        "### Treats\n"
        "Tuna is a popular treat but should be given only in small amounts.\n\n"
        "## Health\n"
        "Annual vaccines and regular vet visits keep cats healthy.\n"
    ),
}

# 1. chunk the note
chunks = chunk_note(note)

# 2. embed the text of every chunk, in one call (batching happens inside)
vectors = embed_texts([c["text"] for c in chunks])

# 3. the two lists line up by position
assert len(vectors) == len(chunks)
print(f"{len(chunks)} chunks -> {len(vectors)} vectors of dimension {len(vectors[0])}\n")


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    return dot / ((sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5))


# 4. embed a question the same way and rank the chunks
for question in ["How long do cats sleep?", "Can I give my cat fish?", "Do cats need shots?"]:
    q = embed_query(question)
    ranked = sorted(zip(chunks, vectors), key=lambda cv: cosine(q, cv[1]), reverse=True)
    best, vec = ranked[0]
    print(f"Q: {question}\n   best: [{best['heading_path']}] similarity {cosine(q, vec):.2f}")
