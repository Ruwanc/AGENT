"""Load, chunk, embed and save every source into ChromaDB.

Run from the project root (Ollama must be running):
    python -m scripts.index            # add new/changed files, remove deleted ones
    python -m scripts.index --force    # re-embed everything
    python -m scripts.index --reset    # delete the collection first, then rebuild
"""
import argparse
import time

from config import CHROMA_DIR, COLLECTION_NAME, EMBEDDING_MODEL, SOURCES
from cet_agent.rag.indexer import sync
from cet_agent.rag.store import reset_collection

parser = argparse.ArgumentParser(description="Index Markdown sources into ChromaDB")
parser.add_argument("--force", action="store_true", help="re-embed files even if unchanged")
parser.add_argument("--reset", action="store_true", help="delete the collection and rebuild it")
args = parser.parse_args()

print(f"DB: {CHROMA_DIR}  collection: {COLLECTION_NAME}  model: {EMBEDDING_MODEL}")
print("Sources: " + ", ".join(f"{s['name']} -> {s['path']}" for s in SOURCES))
if args.reset:
    reset_collection()
    print("[reset] collection deleted")

start = time.time()
stats = sync(force=args.force or args.reset)
print(f"\nDone in {time.time() - start:.1f}s: "
      f"{stats['added']} added, {stats['updated']} updated, {stats['unchanged']} unchanged, "
      f"{stats['deleted']} deleted; {stats['chunks_written']} chunks embedded; "
      f"{stats['total_chunks']} chunks in the DB.")
