"""Health check for embeddings and the vector DB. Prints PASS / WARN / FAIL per check.

    python -m scripts.check_embeddings
    python -m scripts.check_embeddings --question "How do I activate the venv on Windows?" --expect guides/install.md

Checks, in order:
  1. Ollama answers and the model returns vectors (and how fast)
  2. Vector shape: dimension, not all zeros, same input -> same vector
  3. Meaning: similar sentences score higher than unrelated ones
  4. Query prefix: which one is used for questions
  5. DB matches config: same model name, same dimension, has chunks
  6. Self-retrieval: a stored chunk's own text finds that chunk first
  7. (optional) A real question finds the file you expect in the top 3
"""
import argparse
import math
import random
import time

import config
from cet_agent.rag.embeddings import embed_query, embed_texts

results = []


def report(status, name, detail):
    results.append(status)
    print(f"[{status}] {name}: {detail}")


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) or 1)


parser = argparse.ArgumentParser()
parser.add_argument("--question", help="a real question about your documents")
parser.add_argument("--expect", help="note_path that should answer it, e.g. guides/install.md")
parser.add_argument("--samples", type=int, default=5, help="chunks used for the self-retrieval check")
args = parser.parse_args()

print(f"model: {config.EMBEDDING_MODEL}\nquery prefix: {config.QUERY_PREFIX!r}\nDB: {config.CHROMA_DIR}\n")

# 1. Ollama + model
try:
    t = time.time()
    v1, v2 = embed_texts(["Cats sleep a lot.", "Cats sleep a lot."])
    report("PASS", "1 Ollama + model", f"got vectors in {time.time() - t:.2f}s")
except Exception as e:
    report("FAIL", "1 Ollama + model", e)
    raise SystemExit("\nFix this first: start Ollama (`ollama serve`) and pull the model.")

# 2. Vector shape
dim = len(v1)
zero = all(abs(x) < 1e-12 for x in v1)
same = cosine(v1, v2)
report("FAIL" if zero else "PASS", "2 vector shape",
       f"dimension {dim}, first values {[round(x, 3) for x in v1[:4]]}, all zeros: {zero}")
report("PASS" if same > 0.999 else "WARN", "2 repeatable", f"same text twice -> similarity {same:.4f} (expect ~1.0)")

# 3. Meaning
a, b, c = embed_texts(["How do I install Python packages?",
                       "Use pip install to add a library to your environment.",
                       "My cat likes to sleep on the windowsill."])
related, unrelated = cosine(a, b), cosine(a, c)
report("PASS" if related > unrelated + 0.05 else "FAIL", "3 meaning",
       f"related pair {related:.2f} vs unrelated pair {unrelated:.2f} (related must be clearly higher)")

# 4. Query prefix
q_plain = embed_texts(["How do I install Python packages?"])[0]
q_prefixed = embed_query("How do I install Python packages?")
if config.QUERY_PREFIX:
    report("PASS", "4 query prefix", f"prefix in use; prefixed vs plain question similarity "
           f"{cosine(q_plain, q_prefixed):.2f} (below 1.0 = the prefix changes the vector)")
else:
    report("WARN", "4 query prefix", "no prefix for this model; fine if the model needs none")

# 5. DB matches config
from cet_agent.rag.store import get_collection, query
try:
    col = get_collection()
except RuntimeError as e:
    report("FAIL", "5 DB model", e)
    raise SystemExit(1)
count = col.count()
if count == 0:
    report("FAIL", "5 DB contents", "collection is empty; run: python -m scripts.index")
    raise SystemExit(1)
stored = col.get(limit=1, include=["embeddings"])["embeddings"][0]
report("PASS", "5 DB model", f"collection built with {col.metadata.get('embedding_model')}")
report("PASS" if len(stored) == dim else "FAIL", "5 DB dimension",
       f"stored vectors have {len(stored)} numbers, model gives {dim}"
       + ("" if len(stored) == dim else " -> run: python -m scripts.index --reset"))
report("PASS", "5 DB contents", f"{count} chunks stored")

# 6. Self-retrieval: embed a stored chunk's text again and search with it
ids = col.get(include=[])["ids"]
picked = random.sample(ids, min(args.samples, len(ids)))
recs = col.get(ids=picked, include=["documents"])
ok = 0
for cid, doc in zip(recs["ids"], recs["documents"]):
    top = query(col, embed_texts([doc])[0], k=1)
    hit = top and top[0]["id"] == cid
    ok += bool(hit)
    print(f"      {'ok ' if hit else 'MISS'} {cid}  (top similarity {top[0]['similarity']:.3f})")
report("PASS" if ok == len(picked) else "WARN" if ok else "FAIL", "6 self-retrieval",
       f"{ok}/{len(picked)} chunks found themselves first "
       "(misses usually mean near-duplicate chunks, or vectors from another model)")

# 7. A real question
if args.question:
    hits = query(col, embed_query(args.question), k=3)
    for rank, h in enumerate(hits, 1):
        print(f"      #{rank} {h['similarity']:.2f}  {h['note_path']} — {h['heading_path']}")
    if args.expect:
        found = any(h["note_path"] == args.expect for h in hits)
        report("PASS" if found else "FAIL", "7 real question",
               f"{args.expect} {'is' if found else 'is NOT'} in the top 3")
    else:
        report("PASS", "7 real question", "see the top 3 above; add --expect to check automatically")

print(f"\n{results.count('PASS')} passed, {results.count('WARN')} warnings, {results.count('FAIL')} failed")
