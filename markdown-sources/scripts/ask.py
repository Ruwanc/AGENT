"""Ask questions about your documents and get answers with sources.

Run from the project root (Ollama running, index built with `python -m scripts.index`):
    python -m scripts.ask "How do I activate the venv on Windows?"
    python -m scripts.ask "What port does the API use?" --show-context
    python -m scripts.ask                          # chat mode: follow-up questions remember context
    python -m scripts.ask --model qwen3:4b         # try another chat model (default: CHAT_MODEL in config.py)
"""
import argparse
import sys

import config
from md_rag import chat


def print_sources(result, show_context):
    if show_context and result["hits"]:
        print("\n--- context given to the model (searched for: %r) ---" % result["query"])
        print(chat.build_context(result["hits"]))
    if result.get("copied"):
        print("\n(!) The model copied the passages instead of answering. Ask again, or try a "
              "bigger model, e.g. --model qwen3:4b")
    if result["sources"]:
        print("\nSources:")
        for s in result["sources"]:
            mark = "*" if s["cited"] else " "
            extra = ", added: same section" if s.get("expanded") else ""
            print(f" {mark}[{s['n']}] {s['source']}:{s['note_path']} — {s['heading_path']}"
                  f"  (similarity {s['similarity']:.2f}{extra})")
        if not any(s["cited"] for s in result["sources"]):
            print("  (the model did not cite any passage; check the answer against these)")
        else:
            print("  * = cited in the answer")


def run(question, args, history=()):
    print("\nAnswer: ", end="", flush=True)
    result = chat.ask(question, k=args.k, source=args.source, history=history,
                      min_similarity=args.min_similarity, expand=not args.no_expand,
                      on_token=lambda t: print(t, end="", flush=True),
                      chat_fn=lambda m, on_token: chat.ollama_chat(m, model=args.model, on_token=on_token))
    print()
    print_sources(result, args.show_context)
    return result


parser = argparse.ArgumentParser(description="Ask questions about your Markdown documents")
parser.add_argument("question", nargs="?", help="leave out for chat mode")
parser.add_argument("-k", type=int, default=config.ANSWER_TOP_K, help="chunks given to the model")
parser.add_argument("--source", help="only use one source by name")
parser.add_argument("--model", default=config.CHAT_MODEL, help="Ollama chat model")
parser.add_argument("--min-similarity", type=float, default=config.MIN_SIMILARITY,
                    help="chunks below this are ignored (0-1)")
parser.add_argument("--show-context", action="store_true", help="print the passages sent to the model")
parser.add_argument("--no-expand", action="store_true", help="don't add the rest of matched sections")
args = parser.parse_args()

print(f"chat model: {args.model}   embeddings: {config.EMBEDDING_MODEL}")
try:
    if args.question:
        run(args.question, args)
    else:
        print("Chat mode. Blank line quits, 'reset' forgets the conversation.")
        history = []
        while True:
            q = input("\nYou: ").strip()
            if not q:
                break
            if q.lower() == "reset":
                history = []
                print("(conversation cleared)")
                continue
            result = run(q, args, history)
            if result["found"]:
                history = (history + [(q, result["answer"])])[-config.HISTORY_TURNS:]
except RuntimeError as e:          # Ollama not running, model missing, wrong embedding model...
    sys.exit(f"\nError: {e}")
