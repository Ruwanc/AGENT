"""Show what is stored in ChromaDB: counts per source and file, plus sample records.

    python -m scripts.inspect_db
    python -m scripts.inspect_db --file guides/install.md     # every chunk of one file
"""
import argparse
from collections import Counter

from md_rag.store import get_collection

parser = argparse.ArgumentParser()
parser.add_argument("--file", help="note_path to show in full")
args = parser.parse_args()

col = get_collection()
print(f"Collection '{col.name}': {col.count()} chunks   metadata: {col.metadata}")
if col.count() == 0:
    raise SystemExit("Empty. Run: python -m scripts.index")

metas = col.get(include=["metadatas"])["metadatas"]
for (src, path), n in sorted(Counter((m["source"], m["note_path"]) for m in metas).items()):
    print(f"  {src:<10} {path:<40} {n:>3} chunks")

if args.file:
    res = col.get(where={"note_path": args.file}, include=["documents", "metadatas", "embeddings"])
    rows = sorted(zip(res["ids"], res["documents"], res["metadatas"], res["embeddings"]),
                  key=lambda r: r[2]["chunk_index"])
    for cid, doc, meta, emb in rows:
        print(f"\n--- {cid}   ({len(doc)} chars, vector of {len(emb)} numbers: "
              f"[{', '.join(f'{x:.3f}' for x in emb[:4])}, ...])\n{doc}")
