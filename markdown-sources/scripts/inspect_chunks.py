"""Load every source, chunk it, and print a report. No Ollama or Chroma needed.

Run from the project root:
    python -m scripts.inspect_chunks              # all sources
    python -m scripts.inspect_chunks docs         # one source by name
    python -m scripts.inspect_chunks docs --full  # print full chunk text
"""
import sys

from config import MAX_CHUNK_CHARS, SOURCES
from cet_agent.rag.chunking import chunk_note
from cet_agent.rag.sources import chunk_id, load_all

args = [a for a in sys.argv[1:] if not a.startswith("--")]
full = "--full" in sys.argv
sources = [s for s in SOURCES if not args or s["name"] in args]

total, too_big = 0, 0
for doc in load_all(sources):
    chunks = chunk_note(doc)
    total += len(chunks)
    print(f"\n=== [{doc['source']}] {doc['path']}  title={doc['title']!r}  tags={doc['tags']}  "
          f"-> {len(chunks)} chunks")
    for c in chunks:
        size = len(c["text"])
        too_big += size > MAX_CHUNK_CHARS
        flag = "  <-- over limit" if size > MAX_CHUNK_CHARS else ""
        if full:
            print(f"\n--- {chunk_id(c, doc['source'])} ({size} chars){flag}\n{c['text']}")
        else:
            body = c["text"].split("\n\n", 1)[-1][:50].replace("\n", " / ")
            print(f"{c['chunk_index']:>3} {size:>4}  {c['heading_path'][:50]:<50} | {body}{flag}")

print(f"\nTOTAL: {total} chunks, {too_big} over {MAX_CHUNK_CHARS} chars")
