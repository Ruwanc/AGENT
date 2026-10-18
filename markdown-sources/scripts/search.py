"""Ask a question and see which chunks the vector DB returns.

    python -m scripts.search "How do I activate the venv on Windows?"
    python -m scripts.search "port already in use" -k 3 --source docs
    python -m scripts.search                       # interactive: blank line quits
"""
import argparse

from config import TOP_K
from md_rag.retriever import search


def show(question, k, source):
    hits = search(question, k=k, source=source)
    if not hits:
        print("No results. Did you run `python -m scripts.index`?")
    for rank, h in enumerate(hits, 1):
        body = h["text"].split("\n\n", 1)[-1].replace("\n", " ")
        print(f"\n#{rank}  similarity {h['similarity']:.2f}   {h['source']}:{h['note_path']}")
        print(f"    {h['heading_path']}")
        print(f"    {body[:160]}{'…' if len(body) > 160 else ''}")


parser = argparse.ArgumentParser(description="Search the Markdown vector DB")
parser.add_argument("question", nargs="?", help="leave out for interactive mode")
parser.add_argument("-k", type=int, default=TOP_K, help="number of results")
parser.add_argument("--source", help="only search one source by name")
args = parser.parse_args()

if args.question:
    show(args.question, args.k, args.source)
else:
    while (q := input("\nQuestion (blank to quit): ").strip()):
        show(q, args.k, args.source)
