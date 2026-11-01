"""Answer questions from the indexed documents (the "G" in RAG).

    question ──► retriever.search ──► relevance gate ──► prompt ──► Ollama chat ──► answer + sources

1. Retrieve the top chunks for the question.
2. Keep only chunks with similarity >= MIN_SIMILARITY. If none are left, reply
   "not found" WITHOUT calling the chat model (it would only guess).
3. Add the other chunks of each matched section (EXPAND_SECTIONS), so a table that
   was split into pieces reaches the model complete.
4. Put the chunks into the LAST user message as <passage id="1" ...> blocks, then the
   question, then a short reminder to answer in its own words and cite [1], [2].
   (Small models copy text they see in a "list" format; tags + a final reminder help.)
5. Return the answer plus the list of sources, marking which ones it cited, and flag
   answers that copied the passages instead of answering.
"""
import re

from config import ANSWER_TOP_K, CHAT_MODEL, CHAT_TEMPERATURE, EXPAND_SECTIONS, MIN_SIMILARITY

NOT_FOUND = "I couldn't find that in your documents."

SYSTEM_PROMPT = f"""You answer questions about the user's documents.

Rules:
- Use ONLY the passages given in the user's message. Do not add outside knowledge.
- Write the answer in your own words, in plain sentences or a short bullet list.
- Do NOT copy the passages, their <passage> tags, file names or headings into the answer.
- After each fact, cite the passage number in square brackets, like [1] or [2][3].
- If the passages do not contain the answer, reply exactly: "{NOT_FOUND}"
- Copy commands, numbers and names exactly as written.
"""

ANSWER_REMINDER = ("Answer the question above using only the passages. "
                   "Use your own words, cite passages like [1], and do not repeat the passages.")

CITATION_RE = re.compile(r"\[(\d+)\]")
FOLLOW_UP_MAX_WORDS = 6


def build_context(hits):
    """Wrap each chunk in a numbered <passage> tag with its file and section."""
    blocks = []
    for n, h in enumerate(hits, 1):
        body = h["text"].split("\n\n", 1)[-1]          # drop the header line; it is in the tag
        blocks.append(f'<passage id="{n}" file="{h["source"]}:{h["note_path"]}" '
                      f'section="{h["heading_path"]}">\n{body}\n</passage>')
    return "\n\n".join(blocks)


def build_messages(question, hits, history=()):
    """system rules -> earlier turns (plain Q&A) -> one user message: passages, question, reminder."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for q, a in history:
        messages += [{"role": "user", "content": q}, {"role": "assistant", "content": a}]
    messages.append({"role": "user", "content":
                     f"Passages:\n\n{build_context(hits)}\n\nQuestion: {question}\n\n{ANSWER_REMINDER}"})
    return messages


def copied_passages(answer, hits):
    """True if the model pasted passages back instead of answering (common with small models)."""
    low = answer.lower()
    if "<passage" in low or "</passage>" in low:
        return True
    if any(f'{h["source"]}:{h["note_path"]}'.lower() in low for h in hits):
        return True
    return sum(1 for h in hits if h["heading_path"].lower() in low and len(h["heading_path"]) > 25) >= 2


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
             "heading_path": h["heading_path"], "similarity": h["similarity"],
             "expanded": h.get("expanded", False)}
            for n, h in enumerate(hits, 1)]


def ask(question, k=ANSWER_TOP_K, source=None, history=(), min_similarity=MIN_SIMILARITY,
        on_token=None, search_fn=None, chat_fn=None, expand_fn=None, expand=EXPAND_SECTIONS):
    """Answer one question. Returns a dict:

        {"answer": str, "found": bool, "copied": bool, "sources": [...], "hits": [...], "query": str}

    search_fn, chat_fn and expand_fn can be replaced (tests use fakes so no Ollama is needed).
    """
    if search_fn is None:
        from cet_agent.rag.retriever import search as search_fn
    chat_fn = chat_fn or ollama_chat

    query = retrieval_query(question, history)
    hits = [h for h in search_fn(query, k=k, source=source) if h["similarity"] >= min_similarity]
    if not hits:
        if on_token:
            on_token(NOT_FOUND)
        return {"answer": NOT_FOUND, "found": False, "copied": False, "sources": [], "hits": [],
                "query": query}

    if expand:
        if expand_fn is None:
            from cet_agent.rag.retriever import expand_sections as expand_fn
        hits = expand_fn(hits)

    text = chat_fn(build_messages(question, hits, history), on_token=on_token).strip()
    found = NOT_FOUND.lower().rstrip(".") not in text.lower()
    return {"answer": text, "found": found, "copied": found and copied_passages(text, hits),
            "sources": sources_list(hits, text) if found else [], "hits": hits, "query": query}
