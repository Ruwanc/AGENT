# Handoff: local Obsidian RAG project (Python + ChromaDB + Ollama)

Paste or attach this file at the start of a new Claude chat and say: "Continue this project with me. I'm a beginner and want to build it myself, so guide me and review my code instead of writing everything."

## Who I am and what I want
- Beginner learning RAG. I want to build it myself; give plans, explanations and reviews.
- Goal: RAG over my Obsidian vault, fully local, Python + ChromaDB (no LangChain for now).
- Vault: fewer than 50 Markdown files in different folders, some contain images (image embeds are stripped for now).
- Interface: CLI chat first. File watcher for automatic re-indexing.
- Local models in Ollama (already pulled):
  - embeddings: `hf.co/CompendiumLabs/bge-base-en-v1.5-gguf` (768 dimensions)
  - chat: `hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF`

## Earlier learning steps (done)
- Built a small RAG over `cat.txt` (one line = one chunk): `PersistentClient`, `get_or_create_collection` with `hnsw:space: cosine`, batched `ollama.embed`, `upsert` with deterministic IDs, `collection.query(query_embeddings=...)`, streamed `ollama.chat`.
- Lessons: `query()` does not return embeddings unless `include=["embeddings"]`; with cosine space, similarity = 1 - distance; query and documents must use the same embedding model; BGE wants a query prefix on queries only.

## Architecture
- Indexing pipeline: vault scanner -> chunker -> embedder -> ChromaDB (collection `vault_chunks`, cosine).
- Query pipeline: CLI -> retriever (embed query, top-k, filters, distance threshold) -> answer generator (prompt with chunks + note paths, streamed, cites sources).
- Ollama serves both the embedding and chat models.
- Incremental indexing: `data/manifest.json` of `{note_path: content_hash}`. Changed note: delete its old chunks, re-chunk, re-embed, upsert. Deleted note: remove its chunks.
- Watcher: `watchdog`, debounce 2 to 3 s per path, ignore `.obsidian/`, treat move as delete + index, run `sync_vault()` at startup, watcher thread + CLI in ONE process (do not run two processes on the same Chroma folder).

## Planned layout
```
obsidian-rag/
  config.py  main.py  requirements.txt  .gitignore  README.md
  rag/ vault.py chunking.py embeddings.py store.py indexer.py retriever.py chat.py watcher.py
  scripts/ inspect_db.py eval.py
  tests/ test_chunking.py test_vault.py
  data/ chroma_db/  manifest.json   (generated, git-ignored)
```
Dependencies flow one way: config <- vault/chunking/embeddings/store <- indexer/retriever <- chat/watcher <- main.

## Build phases
0 environment; 1 vault.py; 2 chunking.py; 3 embeddings.py + store.py; 4 retriever.py (test before adding LLM); 5 chat.py + main.py (distance gate: "not found in your notes"); 6 indexer.py (manifest, sync_vault); 7 watcher.py; 8 hardening (logging, overlap, MMR, memory, images, eval.py with ~15 questions and top-3 hit rate).

## Status
- DONE: `config.py` (chunking + embedding settings), `rag/chunking.py` (heading-aware, code-fence aware, paragraph packing, sentence fallback, hard-cut last resort, table splitting that repeats the header row), `rag/embeddings.py`, tests for chunking (12 pass).
- Verified: chunk -> embed -> in-memory cosine ranking works with the real bge model (questions found the right section, similarity 0.61 to 0.84).
- NEXT: `vault.py` (list notes, read frontmatter/tags, strip image embeds, SHA-256 hash, vault-relative forward-slash paths), then `store.py` (PersistentClient, cosine collection, IDs like `f"{note_path}::{chunk_index}"`, tags stored as a joined string because Chroma metadata cannot hold lists, `delete_note`, `query` returning clean dicts).

## Known limitations / ideas
- Tiny sections are dropped (could merge into the previous chunk); no chunk overlap; long bullet lists and code blocks still use sentence/hard-cut splitting.
- LangChain discussed: build by hand first, then optionally swap layers (ObsidianLoader, MarkdownHeaderTextSplitter, langchain-chroma, langchain-ollama) or use LangGraph for agentic RAG later.

---
# Current code

## config.py
```python
# Settings are added here as you build each file.

# chunking.py
MAX_CHUNK_CHARS = 800
MIN_CHUNK_CHARS = 30

# embeddings.py
EMBEDDING_MODEL = "hf.co/CompendiumLabs/bge-base-en-v1.5-gguf"
EMBED_BATCH_SIZE = 32
# BGE models work best when the *query* (not the documents) has this prefix.
# Check the model card of the exact model you use; set to "" if it needs none.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
```

## rag/chunking.py
```python
"""Heading-aware chunking for Markdown notes.

Pure text processing: strings in, lists of dicts out. No files, no Ollama, no Chroma.
"""
import re

from config import MAX_CHUNK_CHARS, MIN_CHUNK_CHARS

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")   # "## Diet"; "#tag" has no space, so it is not a heading
FENCE_RE = re.compile(r"^\s*(```|~~~)")              # start/end of a fenced code block
PARAGRAPH_RE = re.compile(r"\n\s*\n")                # blank line(s) between paragraphs
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")           # whitespace after . ! ?


def split_by_headings(body, title=""):
    """Split a note body into (heading_path, text) sections.

    heading_path looks like "Cats > Diet > Treats". Text before the first
    heading gets `title` as its path. Empty sections are dropped.
    """
    sections = []
    stack = []        # [(level, heading_text), ...] for the current position
    buffer = []       # lines of the section being built
    in_fence = False

    def flush():
        text = "\n".join(buffer).strip()
        if text:
            path = " > ".join(h for _, h in stack) or title
            sections.append((path, text))
        buffer.clear()

    for line in body.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            buffer.append(line)
            continue

        match = None if in_fence else HEADING_RE.match(line)
        if match:
            flush()
            level = len(match.group(1))
            while stack and stack[-1][0] >= level:   # leaving deeper/equal sections
                stack.pop()
            stack.append((level, match.group(2)))
        else:
            buffer.append(line)

    flush()
    return sections


def _split_oversized(paragraph, max_chars):
    """Split one too-long paragraph on sentences; hard-split a sentence only as a last resort."""
    pieces, current = [], ""
    for sentence in SENTENCE_RE.split(paragraph):
        while len(sentence) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:max_chars])
            sentence = sentence[max_chars:]

        candidate = f"{current} {sentence}" if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
        else:
            pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    return pieces


def _is_table(paragraph):
    """True if every line of the paragraph starts with '|' (a Markdown table)."""
    lines = paragraph.splitlines()
    return len(lines) >= 2 and all(line.lstrip().startswith("|") for line in lines)


def _split_table(table, max_chars):
    """Split a table between rows, repeating the header and |---| lines in every piece."""
    lines = table.splitlines()
    header = "\n".join(lines[:2])
    pieces, current = [], header
    for row in lines[2:]:
        candidate = f"{current}\n{row}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current != header:            # never emit a header-only piece
                pieces.append(current)
            current = f"{header}\n{row}"
    if current != header:
        pieces.append(current)
    return pieces


def split_long_section(text, max_chars=MAX_CHUNK_CHARS):
    """Pack paragraphs into pieces of at most max_chars characters."""
    if len(text) <= max_chars:
        return [text]

    pieces, current = [], ""
    for paragraph in PARAGRAPH_RE.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        if len(paragraph) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            if _is_table(paragraph):
                pieces.extend(_split_table(paragraph, max_chars))
            else:
                pieces.extend(_split_oversized(paragraph, max_chars))
            continue

        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
        else:                       # current is non-empty here, otherwise candidate would fit
            pieces.append(current)
            current = paragraph

    if current:
        pieces.append(current)
    return pieces


def chunk_note(note, max_chars=MAX_CHUNK_CHARS, min_chars=MIN_CHUNK_CHARS):
    """Turn a note dict ({"path", "title", "tags", "body"}) into a list of chunk dicts.

    The chunk "text" is prefixed with "title > heading path" so that a chunk
    like "Give 5 mg twice daily" still carries its context when embedded.
    """
    title = note.get("title", "")
    chunks = []

    for heading_path, section_text in split_by_headings(note["body"], title):
        for piece in split_long_section(section_text, max_chars):
            if len(piece) < min_chars:
                continue

            if not title or heading_path.startswith(title):
                header = heading_path
            else:
                header = f"{title} > {heading_path}"

            chunks.append({
                "text": f"{header}\n\n{piece}",
                "note_path": note["path"],
                "heading_path": heading_path,
                "tags": note.get("tags", []),
                "chunk_index": len(chunks),
            })
    return chunks


if __name__ == "__main__":
    demo = {
        "path": "Pets/Cats.md",
        "title": "Cats",
        "tags": ["pets"],
        "body": "Intro about cats and why people keep them.\n\n# Cats\n## Diet\nCats are obligate carnivores and need meat.\n### Treats\nTuna is a popular treat but should be limited.\n## Health\nAnnual vaccines are recommended by vets.\n",
    }
    for c in chunk_note(demo):
        print(c["chunk_index"], "|", c["heading_path"], "|", c["text"].replace("\n", " / "))
```

## rag/embeddings.py
```python
"""The only file that talks to Ollama for vectors.

Chunks and queries must be embedded with the same model, so both go through here.
"""
import ollama

from config import EMBED_BATCH_SIZE, EMBEDDING_MODEL, QUERY_PREFIX


def _embed(batch):
    """One Ollama call. Returns one vector per input string, in the same order."""
    try:
        return ollama.embed(model=EMBEDDING_MODEL, input=batch)["embeddings"]
    except ConnectionError as e:
        raise RuntimeError("Cannot reach Ollama. Is it running? Try: ollama serve") from e


def embed_texts(texts, batch_size=EMBED_BATCH_SIZE):
    """Embed many strings (used for chunks). Output order matches input order."""
    if any(not t.strip() for t in texts):
        raise ValueError("embed_texts got an empty string; filter empties before embedding")

    vectors = []
    for start in range(0, len(texts), batch_size):
        vectors.extend(_embed(texts[start:start + batch_size]))
    return vectors


def embed_query(query):
    """Embed one search question (used by the retriever). Adds the query prefix."""
    return _embed([QUERY_PREFIX + query])[0]


if __name__ == "__main__":
    vecs = embed_texts(["Cats sleep a lot.", "Kittens nap all day.", "The engine needs an oil change."])
    print("vectors:", len(vecs), "dimension:", len(vecs[0]))
```

## tests/test_chunking.py
```python
from rag.chunking import chunk_note, split_by_headings, split_long_section


def test_nested_headings_give_paths():
    body = "# Cats\nIntro.\n## Diet\nMeat.\n### Treats\nTuna.\n## Health\nVaccines."
    paths = [p for p, _ in split_by_headings(body)]
    assert paths == ["Cats", "Cats > Diet", "Cats > Diet > Treats", "Cats > Health"]


def test_text_before_first_heading_uses_title():
    sections = split_by_headings("Loose text.\n# A\nBody.", title="My Note")
    assert sections[0] == ("My Note", "Loose text.")


def test_heading_inside_code_fence_is_ignored():
    body = "# Setup\n```bash\n# install deps\npip install x\n```\nDone."
    paths = [p for p, _ in split_by_headings(body)]
    assert paths == ["Setup"]


def test_obsidian_tag_is_not_a_heading():
    sections = split_by_headings("# A\n#tag in text")
    assert len(sections) == 1 and "#tag" in sections[0][1]


def test_empty_section_is_dropped():
    paths = [p for p, _ in split_by_headings("# A\n# B\nText.")]
    assert paths == ["B"]


def test_long_section_respects_cap():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 40 for i in range(20))
    pieces = split_long_section(text, max_chars=500)
    assert len(pieces) > 1
    assert all(len(p) <= 500 for p in pieces)


def test_giant_single_paragraph_is_still_split():
    pieces = split_long_section("x" * 2500, max_chars=1000)
    assert all(len(p) <= 1000 for p in pieces)
    assert "".join(pieces) == "x" * 2500


def _make_table(n_rows):
    rows = "\n".join(f"| Food{i} | Type{i} | Weekly |" for i in range(n_rows))
    return "| Food | Type | Frequency |\n|---|---|---|\n" + rows


def test_small_table_stays_whole():
    table = _make_table(3)
    assert split_long_section("Intro.\n\n" + table, max_chars=500) == ["Intro.\n\n" + table]


def test_big_table_splits_between_rows_and_repeats_header():
    table = _make_table(20)
    pieces = split_long_section(table, max_chars=150)
    assert len(pieces) > 1
    for p in pieces:
        assert len(p) <= 150
        assert p.startswith("| Food | Type | Frequency |\n|---|---|---|")
        assert all(line.endswith("|") for line in p.splitlines())   # no half rows
    body_rows = [l for p in pieces for l in p.splitlines()[2:]]
    assert body_rows == table.splitlines()[2:]                       # every row kept, in order


def test_text_with_pipes_is_not_treated_as_table():
    text = "a | b " * 100
    assert all(len(p) <= 100 for p in split_long_section(text, max_chars=100))


def test_chunk_note_fields_and_prefix():
    note = {"path": "Pets/Cats.md", "title": "Cats", "tags": ["pets"],
            "body": "## Diet\nCats are obligate carnivores and need meat."}
    chunks = chunk_note(note, min_chars=10)
    assert len(chunks) == 1
    c = chunks[0]
    assert c["text"].startswith("Cats > Diet\n\n")
    assert c["note_path"] == "Pets/Cats.md" and c["chunk_index"] == 0


def test_tiny_chunks_are_skipped():
    note = {"path": "a.md", "title": "A", "tags": [], "body": "# H\nhi"}
    assert chunk_note(note, min_chars=30) == []
```

## scripts_try_chunks_and_embeddings.py
```python
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
```

## rag_cat.py
```python
import argparse

import chromadb
import ollama

EMBEDDING_MODEL = 'hf.co/CompendiumLabs/bge-base-en-v1.5-gguf'
LANGUAGE_MODEL = 'hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF'
DATA_FILE = "cat.txt"
DB_PATH = "./chroma_db"
COLLECTION_NAME = "cat_data_collection"
BATCH = 32

client = chromadb.PersistentClient(path=DB_PATH)
collection = client.get_or_create_collection(
    name=COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"},
)


def index_file(path=DATA_FILE):
    """Read the file, embed each non-empty line, and upsert into Chroma."""
    with open(path, "r", encoding="utf-8") as f:
        dataset = [line.strip() for line in f if line.strip()]
    print("Total lines:", len(dataset))

    for start in range(0, len(dataset), BATCH):
        batch = dataset[start:start + BATCH]
        embeddings = ollama.embed(model=EMBEDDING_MODEL, input=batch)['embeddings']
        collection.upsert(
            ids=[str(start + i) for i in range(len(batch))],
            documents=batch,
            embeddings=embeddings,
            metadatas=[{"source": path, "line": start + i} for i in range(len(batch))],
        )
        print(f"Added {start + len(batch)}/{len(dataset)}")


def view_collection(n=5):
    """Print the record count and the first n records."""
    print("Records in collection:", collection.count())
    res = collection.get(limit=n, include=["documents", "metadatas"])
    for id_, doc, meta in zip(res["ids"], res["documents"], res["metadatas"]):
        print(f"[{id_}] {meta} {doc[:100]}")


def retrieve(query, top_n=3):
    """Return the top_n (chunk, cosine_similarity) pairs for the query."""
    q = ollama.embed(model=EMBEDDING_MODEL, input=query)['embeddings'][0]
    res = collection.query(
        query_embeddings=[q],
        n_results=top_n,
        include=["documents", "distances"],
    )
    # cosine distance -> similarity
    return [(doc, 1 - dist) for doc, dist in zip(res["documents"][0], res["distances"][0])]


def answer(query, top_n=3):
    """Retrieve context, build a prompt, and stream the model's answer."""
    chunks = retrieve(query, top_n)
    print("\nRetrieved knowledge:")
    for chunk, sim in chunks:
        print(f"  (similarity: {sim:.2f}) {chunk}")

    context = "\n".join(f" - {chunk}" for chunk, _ in chunks)
    system_prompt = (
        "You are a helpful chatbot. Use only the following pieces of context "
        "to answer the question. If the answer is not in the context, say you "
        "don't know. Don't make up new information.\n"
        f"Context:\n{context}"
    )

    print("\nChatbot response:")
    stream = ollama.chat(
        model=LANGUAGE_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        stream=True,
    )
    for part in stream:
        print(part["message"]["content"], end="", flush=True)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simple RAG over cat.txt with Ollama + ChromaDB")
    parser.add_argument("--reindex", action="store_true", help="(re)build the index from cat.txt")
    parser.add_argument("--view", action="store_true", help="print the first records and exit")
    args = parser.parse_args()

    # Index automatically the first time, or when asked
    if args.reindex or collection.count() == 0:
        index_file()

    if args.view:
        view_collection()
    else:
        while True:
            q = input("\nAsk me a question (blank to quit): ").strip()
            if not q:
                break
            answer(q)
```
