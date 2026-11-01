"""A simple web chat for the agent: ask about your docs, or request an AWS account.

Run from the project root (Ollama running, index built with `python -m scripts.index`):
    streamlit run ui/chat_app.py
Then open the link it prints (http://localhost:8501).

Try it without Ollama (canned answers, nothing real is called):
    AGENT_UI_DEMO=1 streamlit run ui/chat_app.py

The page only talks to cet_agent.agent.router.Agent, the same object scripts/agent.py uses, so the
UI and the terminal chat behave the same way.
"""
import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # so "import config" works

import config                                   # noqa: E402
from cet_agent.rag import chat                         # noqa: E402
from cet_agent.agent.router import Agent                  # noqa: E402
from cet_agent.integrations.servicenow import get_client        # noqa: E402

DEMO = os.environ.get("AGENT_UI_DEMO") == "1"
MODES = ["fake", "dry_run", "live"]

# Your logo: save it as ui/logo.png (or .jpg / .svg), or point AGENT_UI_LOGO at a file.
# It replaces the tab icon, the title icon and the agent's chat avatar. No file = emoji icons.
UI_DIR = Path(__file__).resolve().parent
LOGO = next((p for p in [Path(os.environ.get("AGENT_UI_LOGO", "")),
                         *(UI_DIR / f"logo.{ext}" for ext in ("png", "jpg", "jpeg", "svg"))]
             if p.name and p.is_file()), None)
AGENT_AVATAR = str(LOGO) if LOGO else "assistant"

st.set_page_config(page_title="CET Agent", page_icon=str(LOGO) if LOGO else "💬",
                   layout="centered")
if LOGO:
    st.logo(str(LOGO), size="large")          # top of the sidebar


# ---------------------------------------------------------------- answer functions
def demo_answer(question, on_token=None):
    text = f"(demo) This is where the answer from your documents would appear for: {question}"
    if on_token:
        on_token(text)
    return {"answer": text, "sources": [{"note_path": "tags.md", "heading_path": "Demo section",
                                         "cited": True, "similarity": 0.9}]}


def rag_answer(question, on_token=None):
    if DEMO:
        return demo_answer(question, on_token)
    model = st.session_state.model
    return chat.ask(question, on_token=on_token,
                    chat_fn=lambda m, on_token: chat.ollama_chat(m, model=model, on_token=on_token))


def new_agent():
    """Fresh agent + empty chat, using the settings in the sidebar."""
    st.session_state.agent = Agent(
        requester=st.session_state.requester.strip(),
        answer_fn=rag_answer,                                 # replaced per message below
        extract_fn=(lambda *a: {}) if DEMO else None,         # demo: no LLM extraction
        servicenow=get_client(st.session_state.mode),
    )
    st.session_state.messages = []


# ---------------------------------------------------------------- state
st.session_state.setdefault("requester", config.REQUESTER_EMAIL)
st.session_state.setdefault("mode", config.SERVICENOW_MODE if config.SERVICENOW_MODE in MODES else "fake")
st.session_state.setdefault("model", config.CHAT_MODEL)
if "agent" not in st.session_state:
    new_agent()

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("Settings")
    st.text_input("Your email", key="requester", placeholder="you@company.com",
                  help="Used as 'Requested for' on AWS account requests.")
    st.selectbox("ServiceNow mode", MODES, key="mode",
                 help="fake = save a JSON ticket in data/servicenow/ · dry_run = show the payload · "
                      "live = real ServiceNow (needs .env)")
    st.text_input("Chat model", key="model", help="Any model you have pulled in Ollama.")
    if st.button("New conversation", use_container_width=True):
        new_agent()
        st.rerun()
    st.caption("Settings apply to a new conversation.")
    if DEMO:
        st.warning("Demo mode: no Ollama, canned answers.")
    st.divider()
    st.caption("Try:\n- What are the mandatory Azure tags?\n- I need a new AWS account\n- cancel")

# ---------------------------------------------------------------- chat
if LOGO:
    icon, heading = st.columns([1, 9], vertical_alignment="center")
    icon.image(str(LOGO), width=56)
    heading.title("CET Agent")
else:
    st.title("💬 CET Agent")
st.caption("Ask about your documents, or say \"I need a new AWS account\".")


def show_sources(sources):
    cited = [s for s in sources if s.get("cited")] or sources[:2]
    if cited:
        with st.expander("Sources"):
            for s in cited:
                st.markdown(f"- `{s['note_path']}` — {s['heading_path']}")


def show_ticket(ticket):
    if not ticket or not ticket.get("number"):
        return
    st.success(f"Ticket **{ticket['number']}** created ({ticket['mode']}).")
    if ticket.get("url"):
        st.markdown(f"[Open in ServiceNow]({ticket['url']})")
    elif ticket.get("path"):
        st.caption(f"Saved to {ticket['path']}")


for m in st.session_state.messages:
    with st.chat_message(m["role"], avatar=AGENT_AVATAR if m["role"] == "assistant" else None):
        st.markdown(m["content"])
        if m.get("sources"):
            show_sources(m["sources"])
        if m.get("ticket"):
            show_ticket(m["ticket"])

if prompt := st.chat_input("Type your message"):
    agent = st.session_state.agent
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant", avatar=AGENT_AVATAR):
        box = st.empty()
        streamed = []

        def on_token(t):
            streamed.append(t)
            box.markdown("".join(streamed) + "▌")

        # Inside a request, side questions are answered quietly (the intake adds the
        # answer to its own reply). Outside a request, the answer streams onto the page.
        if agent.intake:
            agent.answer_fn = lambda q: rag_answer(q)
        else:
            agent.answer_fn = lambda q: rag_answer(q, on_token=on_token)

        try:
            with st.spinner("Thinking..."):
                reply = agent.handle(prompt)
        except RuntimeError as e:                     # e.g. Ollama not running, model missing
            box.empty()
            st.error(str(e))
            st.session_state.messages.append({"role": "assistant", "content": f"⚠ {e}"})
        else:
            if reply.kind == "intake":
                text = reply.text.replace("\n", "  \n")           # keep the line breaks
                if reply.data.get("ticket", {}) and reply.data["ticket"].get("mode") == "dry_run":
                    text = reply.text.replace("This is what would be sent:\n",
                                              "This is what would be sent:\n\n```json\n") + "\n```"
                box.markdown(text)
                ticket = reply.data.get("ticket")
                show_ticket(ticket)
                st.session_state.messages.append({"role": "assistant", "content": text,
                                                  "ticket": ticket})
            else:
                text = reply.data.get("answer", "") or "".join(streamed)
                box.markdown(text)
                sources = reply.data.get("sources", [])
                show_sources(sources)
                st.session_state.messages.append({"role": "assistant", "content": text,
                                                  "sources": sources})
