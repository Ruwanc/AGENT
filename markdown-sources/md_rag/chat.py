"""Answer questions from the indexed documents (the "G" in RAG).

    question ──► retriever.search ──► relevance gate ──► prompt ──► Ollama chat ──► answer + sources

1. Retrieve the top chunks for the question.
2. Keep only chunks with similarity >= MIN_SIMILARITY. If none are left, reply
   "not found" WITHOUT calling the chat model (it would only guess).
3. Put the chunks into the prompt, numbered [1], [2], ... with their file and heading.
4. Ask the chat model to answer only from those chunks and cite the numbers.
5. Return the answer plus the list of sources, marking which ones it cited.
"""
import re

from config import ANSWER_TOP_K, CHAT_MODEL, CHAT_TEMPERATURE, MIN_SIMILARITY

NOT_FOUND = "I couldn't find that in your documents."

SYSTEM_PROMPT = f"""You are a helpful assistant that answers questions about the user's documents.

Rules:
- Use ONLY the numbered context passages below. Do not use outside knowledge.
- After each fact, cite the passage it came from, like [1] or [2][3].
- If the passages do not contain the answer, reply exactly: "{NOT_FOUND}"
- Keep the answer short and direct. Copy commands, numbers and names exactly as written.
"""

CITATION_RE = re.compile(r"\[(\d+)\]")
FOLLOW_UP_MAX_WORDS = 6


def build_context(hits):
    """Number the chunks so the model can cite them: '[1] docs:guides/install.md — Steps'."""
    blocks = []
    for n, h in enumerate(hits, 1):
        body = h["text"].split("\n\n", 1)[-1]          # drop the header line, we show it below
        blocks.append(f"[{n}] {h['source']}:{h['note_path']} — {h['heading_path']}\n{body}")
    return "\n\n".join(blocks)


def build_messages(question, hits, history=()):
    """Messages for Ollama: system rules + context, earlier turns, then the question."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT + "\nContext:\n\n" + build_context(hits)}]
    for q, a in history:
        messages += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
    messages.append({"role": "user", "content": question})
    return messages


def retrieval_query(question, history=()):
    """Short follow-ups ("and on Windows?") don't say what they are about, so they are
    searched together with the previous question. Normal questions are searched as-is."""
    if history and len(question.split()) <= FOLLOW_UP_MAX_WORDS:
        return f"{history[-1][0]} {question}"
    return question


def ollama_chat(messages, model=CHAT_MODEL, on_token=None):
    """Stream one reply from Ollama; call on_token for each piece; return the full text."""
    import ollama
    try:
        stream = ollama.chat(model=model, messages=messages, stream=True,
                             options={"temperature": CHAT_TEMPERATURE})
        parts = []
        for part in stream:
            piece = part["message"]["content"]      # "thinking" text (qwen3) is a separate field
            if piece:
                parts.append(piece)
                if on_token:
                    on_token(piece)
        return "".join(parts)
    except ConnectionError as e:
        raise RuntimeError("Cannot reach Ollama. Is it running? Try: ollama serve") from e
    except ollama.ResponseError as e:
        if e.status_code == 404:
            raise RuntimeError(f"Chat model not found. Run: ollama pull {model}") from e
        raise


def sources_list(hits, answer_text):
    """One entry per context passage, in prompt order, flagged if the answer cited it."""
    cited = {int(n) for n in CITATION_RE.findall(answer_text)}
    return [{"n": n, "cited": n in cited, "source": h["source"], "note_path": h["note_path"],
             "heading_path": h["heading_path"], "similarity": h["similarity"]}
            for n, h in enumerate(hits, 1)]


def ask(question, k=ANSWER_TOP_K, source=None, history=(), min_similarity=MIN_SIMILARITY,
        on_token=None, search_fn=None, chat_fn=None):
    """Answer one question. Returns a dict:

        {"answer": str, "found": bool, "sources": [...], "hits": [...], "query": str}

    search_fn and chat_fn can be replaced (tests use fakes so no Ollama is needed).
    """
    if search_fn is None:
        from md_rag.retriever import search as search_fn
    chat_fn = chat_fn or ollama_chat

    query = retrieval_query(question, history)
    hits = [h for h in search_fn(query, k=k, source=source) if h["similarity"] >= min_similarity]
    if not hits:
        if on_token:
            on_token(NOT_FOUND)
        return {"answer": NOT_FOUND, "found": False, "sources": [], "hits": [], "query": query}

    text = chat_fn(build_messages(question, hits, history), on_token=on_token).strip()
    found = NOT_FOUND.lower().rstrip(".") not in text.lower()
    return {"answer": text, "found": found, "sources": sources_list(hits, text) if found else [],
            "hits": hits, "query": query}
