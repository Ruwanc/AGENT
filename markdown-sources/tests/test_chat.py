"""Answering tests with a fake search and a fake chat model (no Ollama needed)."""
from md_rag import chat


def hit(n, sim, text="Some text.", path="guides/install.md", heading="Install > Steps"):
    return {"id": f"docs:{path}::{n}", "text": f"Title > {heading}\n\n{text}", "similarity": sim,
            "distance": 1 - sim, "source": "docs", "note_path": path, "heading_path": heading}


def fake_search(hits):
    calls = []
    def search(query, k, source):
        calls.append({"query": query, "k": k, "source": source})
        return hits[:k]
    search.calls = calls
    return search


def fake_chat(reply):
    seen = []
    def chat_fn(messages, on_token=None):
        seen.append(messages)
        if on_token:
            on_token(reply)
        return reply
    chat_fn.seen = seen
    return chat_fn


def test_no_relevant_chunks_means_not_found_and_no_llm_call():
    llm = fake_chat("should not be used")
    r = chat.ask("What is the capital of France?", search_fn=fake_search([hit(0, 0.20)]),
                 chat_fn=llm, min_similarity=0.45)
    assert r["answer"] == chat.NOT_FOUND and r["found"] is False
    assert llm.seen == []


def test_low_similarity_chunks_are_dropped_from_the_prompt():
    llm = fake_chat("Use venv [1].")
    hits = [hit(0, 0.80, "Run python -m venv .venv."), hit(1, 0.30, "Unrelated tuna treats.")]
    r = chat.ask("How do I make a venv?", search_fn=fake_search(hits), chat_fn=llm, min_similarity=0.45)
    prompt = llm.seen[0][0]["content"]
    assert "python -m venv .venv" in prompt and "tuna" not in prompt
    assert len(r["hits"]) == 1


def test_prompt_has_rules_numbered_context_and_question():
    llm = fake_chat("Answer [2].")
    hits = [hit(0, 0.9, "First passage."), hit(1, 0.8, "Second passage.", heading="Install > Troubleshooting")]
    chat.ask("Why does the port fail?", search_fn=fake_search(hits), chat_fn=llm)
    system, user = llm.seen[0][0], llm.seen[0][-1]
    assert system["role"] == "system" and "ONLY the numbered context" in system["content"]
    assert "[1] docs:guides/install.md — Install > Steps\nFirst passage." in system["content"]
    assert "[2] docs:guides/install.md — Install > Troubleshooting\nSecond passage." in system["content"]
    assert user == {"role": "user", "content": "Why does the port fail?"}


def test_sources_mark_which_passages_were_cited():
    hits = [hit(0, 0.9), hit(1, 0.8), hit(2, 0.7)]
    r = chat.ask("q", search_fn=fake_search(hits), chat_fn=fake_chat("Do X [1]. Then Y [3]."))
    assert [s["cited"] for s in r["sources"]] == [True, False, True]
    assert r["found"] is True


def test_model_saying_not_found_is_reported_as_not_found():
    r = chat.ask("q", search_fn=fake_search([hit(0, 0.9)]),
                 chat_fn=fake_chat("I couldn't find that in your documents."))
    assert r["found"] is False and r["sources"] == []


def test_history_is_sent_and_short_follow_ups_search_with_previous_question():
    search = fake_search([hit(0, 0.9)])
    llm = fake_chat("On Windows use .venv\\Scripts\\activate [1].")
    history = [("How do I activate the virtual environment?", "Run source .venv/bin/activate [1].")]
    chat.ask("And on Windows?", history=history, search_fn=search, chat_fn=llm)
    assert search.calls[0]["query"] == "How do I activate the virtual environment? And on Windows?"
    roles = [m["role"] for m in llm.seen[0]]
    assert roles == ["system", "user", "assistant", "user"]


def test_long_questions_are_searched_as_is_even_with_history():
    search = fake_search([hit(0, 0.9)])
    history = [("Old question?", "Old answer [1].")]
    q = "What should I do if the port is already in use by another process?"
    chat.ask(q, history=history, search_fn=search, chat_fn=fake_chat("x [1]"))
    assert search.calls[0]["query"] == q


def test_tokens_are_streamed_to_callback():
    got = []
    chat.ask("q", search_fn=fake_search([hit(0, 0.9)]), chat_fn=fake_chat("Hello [1]."),
             on_token=got.append)
    assert "".join(got) == "Hello [1]."
