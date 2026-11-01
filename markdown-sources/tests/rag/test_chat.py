"""Answering tests with a fake search and a fake chat model (no Ollama needed)."""
from cet_agent.rag import chat


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


def ask(*args, **kw):
    """chat.ask without section expansion unless a test asks for it (no DB needed)."""
    kw.setdefault("expand", False)
    return chat.ask(*args, **kw)


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
    r = ask("What is the capital of France?", search_fn=fake_search([hit(0, 0.20)]),
                 chat_fn=llm, min_similarity=0.45)
    assert r["answer"] == chat.NOT_FOUND and r["found"] is False
    assert llm.seen == []


def test_low_similarity_chunks_are_dropped_from_the_prompt():
    llm = fake_chat("Use venv [1].")
    hits = [hit(0, 0.80, "Run python -m venv .venv."), hit(1, 0.30, "Unrelated tuna treats.")]
    r = ask("How do I make a venv?", search_fn=fake_search(hits), chat_fn=llm, min_similarity=0.45)
    prompt = llm.seen[0][-1]["content"]
    assert "python -m venv .venv" in prompt and "tuna" not in prompt
    assert len(r["hits"]) == 1


def test_prompt_has_rules_tagged_passages_question_and_reminder():
    llm = fake_chat("Answer [2].")
    hits = [hit(0, 0.9, "First passage."), hit(1, 0.8, "Second passage.", heading="Install > Troubleshooting")]
    ask("Why does the port fail?", search_fn=fake_search(hits), chat_fn=llm)
    system, user = llm.seen[0][0], llm.seen[0][-1]
    assert system["role"] == "system" and "Do NOT copy the passages" in system["content"]
    assert "passage" not in system["content"].split("Rules:")[0]     # no passages in the system prompt
    c = user["content"]
    assert '<passage id="1" file="docs:guides/install.md" section="Install > Steps">\nFirst passage.\n</passage>' in c
    assert '<passage id="2" file="docs:guides/install.md" section="Install > Troubleshooting">' in c
    assert c.index("</passage>") < c.index("Question: Why does the port fail?") < c.index(chat.ANSWER_REMINDER)


def test_sources_mark_which_passages_were_cited():
    hits = [hit(0, 0.9), hit(1, 0.8), hit(2, 0.7)]
    r = ask("q", search_fn=fake_search(hits), chat_fn=fake_chat("Do X [1]. Then Y [3]."))
    assert [s["cited"] for s in r["sources"]] == [True, False, True]
    assert r["found"] is True


def test_model_saying_not_found_is_reported_as_not_found():
    r = ask("q", search_fn=fake_search([hit(0, 0.9)]),
                 chat_fn=fake_chat("I couldn't find that in your documents."))
    assert r["found"] is False and r["sources"] == []


def test_history_is_sent_and_short_follow_ups_search_with_previous_question():
    search = fake_search([hit(0, 0.9)])
    llm = fake_chat("On Windows use .venv\\Scripts\\activate [1].")
    history = [("How do I activate the virtual environment?", "Run source .venv/bin/activate [1].")]
    ask("And on Windows?", history=history, search_fn=search, chat_fn=llm)
    assert search.calls[0]["query"] == "How do I activate the virtual environment? And on Windows?"
    roles = [m["role"] for m in llm.seen[0]]
    assert roles == ["system", "user", "assistant", "user"]
    assert llm.seen[0][1]["content"] == "How do I activate the virtual environment?"   # history has no passages


def test_long_questions_are_searched_as_is_even_with_history():
    search = fake_search([hit(0, 0.9)])
    history = [("Old question?", "Old answer [1].")]
    q = "What should I do if the port is already in use by another process?"
    ask(q, history=history, search_fn=search, chat_fn=fake_chat("x [1]"))
    assert search.calls[0]["query"] == q


def test_tokens_are_streamed_to_callback():
    got = []
    ask("q", search_fn=fake_search([hit(0, 0.9)]), chat_fn=fake_chat("Hello [1]."),
             on_token=got.append)
    assert "".join(got) == "Hello [1]."


def test_copied_passages_are_flagged():
    hits = [hit(0, 0.9, heading="Pet Care Handbook > Diet > Food Reference")]
    copied = '[1] docs:guides/install.md — Pet Care Handbook > Diet > Food Reference\n| Food | Type |'
    r = ask("q", search_fn=fake_search(hits), chat_fn=fake_chat(copied))
    assert r["copied"] is True
    r = ask("q", search_fn=fake_search(hits), chat_fn=fake_chat("Cats can eat cooked chicken [1]."))
    assert r["copied"] is False


def test_sections_are_expanded_before_the_prompt():
    llm = fake_chat("Chicken and turkey are safe [1].")
    matched = hit(9, 0.7, "| Pumpkin | Yes |", heading="Diet > Food Reference")
    sibling = {**hit(8, 0.0, "| Chicken | Yes |", heading="Diet > Food Reference"), "expanded": True}
    r = ask("Which foods are safe for cats?", search_fn=fake_search([matched]), chat_fn=llm,
            expand=True, expand_fn=lambda hits: [sibling] + hits)
    prompt = llm.seen[0][-1]["content"]
    assert prompt.index("Chicken") < prompt.index("Pumpkin")
    assert [s["expanded"] for s in r["sources"]] == [True, False]
