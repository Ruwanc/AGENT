"""CET Provisioner: enterprise chat UI for the CET agent (the "CET Agent UI Concept" design).

    streamlit run ui/cet_assistant.py
    AGENT_UI_DEMO=1 streamlit run ui/cet_assistant.py     # canned answers, no Ollama

A second UI for the same agent as ui/chat_app.py (which stays as it is): same answers,
same cloud account requests (ENABLED_CLOUDS), same ServiceNow modes. What this one adds:
  - a left panel with "New chat", the chats of this browser session and your requests
  - ChatGPT-style chat: your messages as blue bubbles, the agent's replies as plain text
  - source chips under answers, a progress card while a request is being filled in
  - quick-reply buttons (submit, cancel) and starter questions on a new chat

Brand: set BRAND to your corporate blue, and save your logo as ui/logo.png (or .svg).
"""
import base64
import html
import json
import os
import sys
import uuid
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # so "import config" works

import config                                              # noqa: E402
from cet_agent.agent.router import Agent, parse_enabled    # noqa: E402
from cet_agent.integrations.servicenow import get_client   # noqa: E402
from cet_agent.rag import chat                             # noqa: E402

DEMO = os.environ.get("AGENT_UI_DEMO") == "1"
MODES = ["fake", "dry_run", "live"]

# ---- brand ---------------------------------------------------------------------------------
BRAND = os.environ.get("AGENT_UI_BRAND", "#0A5BA8")       # corporate blue (replace with the exact hex)
UI_DIR = Path(__file__).resolve().parent
LOGO = next((p for p in [Path(os.environ.get("AGENT_UI_LOGO", "")),
                         *(UI_DIR / f"logo.{e}" for e in ("svg", "png", "jpg", "jpeg"))]
             if p.name and p.is_file()), None)

# Starter questions follow ENABLED_CLOUDS: one request button per enabled cloud
CLOUDS = parse_enabled(config.ENABLED_CLOUDS)
REQUEST_STARTERS = {"aws": ("New AWS account", "I need a new AWS account"),
                    "gcp": ("New GCP project", "I need a new GCP project")}
STARTERS = [("Tagging standard", "What are the mandatory tags?")] + [REQUEST_STARTERS[c] for c in CLOUDS]
WHAT = " or ".join({"aws": "a new AWS account", "gcp": "a new GCP project"}[c] for c in CLOUDS)

st.set_page_config(page_title="CET Provisioner", page_icon=str(LOGO) if LOGO else "☁️",
                   layout="wide", initial_sidebar_state="expanded")


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    h = "".join(c * 2 for c in h) if len(h) == 3 else h
    return ",".join(str(int(h[i:i + 2], 16)) for i in (0, 2, 4))


def _logo_html(size, radius):
    if LOGO:
        kind = "svg+xml" if LOGO.suffix == ".svg" else LOGO.suffix.lstrip(".").replace("jpg", "jpeg")
        data = base64.b64encode(LOGO.read_bytes()).decode()
        return (f'<img src="data:image/{kind};base64,{data}" alt="logo" '
                f'style="width:{size}px;height:{size}px;border-radius:{radius}px;object-fit:contain">')
    return f'<div class="cet-logo-ph" style="width:{size}px;height:{size}px;border-radius:{radius}px">LOGO</div>'


RGB = _rgb(BRAND)

# ---- look -----------------------------------------------------------------------------------
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
:root {{ --brand:{BRAND}; --tint:rgba({RGB},.08); --glow:rgba({RGB},.14);
        --ink:#18212B; --text:#3A4654; --muted:#5B6878; --line:#E6EBF1; --side:#F7F9FC; }}
.stApp, .stApp p, .stApp li, .stApp h1, .stApp h2, .stApp h3, .stApp label,
.stButton button, .stApp textarea, .stApp input {{
    font-family:'Plus Jakarta Sans', system-ui, -apple-system, 'Segoe UI', sans-serif; }}
[data-testid="stIconMaterial"] {{ font-family:'Material Symbols Rounded' !important; }}
code, .cet-mono {{ font-family:'JetBrains Mono', ui-monospace, monospace !important; }}
#MainMenu, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] {{ display:none; }}
[data-testid="stHeader"] {{ background:transparent; }}

/* page: white with a soft light-blue glow at the top */
.stApp {{ background: radial-gradient(900px 380px at 55% -80px, var(--glow), rgba(255,255,255,0) 70%),
                      linear-gradient(180deg,#FFFFFF 0%,#FBFCFE 100%); color:var(--ink); }}
.block-container {{ max-width:820px; padding-top:1.5rem; padding-bottom:7rem; }}

/* left panel */
[data-testid="stSidebar"] {{ background:var(--side); border-right:1px solid var(--line); }}
[data-testid="stSidebar"] .block-container, [data-testid="stSidebarUserContent"] {{ padding-top:1rem; }}
.cet-brand {{ display:flex; align-items:center; gap:12px; padding:2px 4px 8px; }}
.cet-brand .n {{ font-size:16px; font-weight:700; color:var(--ink); line-height:1.2; }}
.cet-brand .s {{ font-size:12px; color:var(--muted); }}
.cet-logo-ph {{ border:1px dashed #A9B6C6; display:flex; align-items:center; justify-content:center;
               font-size:8px; font-weight:600; color:var(--muted); letter-spacing:.04em; flex:none; }}
.cet-label {{ font-size:12px; font-weight:600; color:var(--muted); letter-spacing:.02em; margin:14px 6px 4px; }}
[data-testid="stSidebar"] .stButton > button {{ width:100%; justify-content:flex-start; text-align:left;
    border-radius:10px; border:1px solid transparent; background:transparent; color:var(--text);
    padding:8px 12px; font-size:14px; min-height:40px; }}
[data-testid="stSidebar"] .stButton > button:hover {{ background:var(--tint); color:var(--ink); border-color:transparent; }}
.st-key-newchat .stButton > button {{ background:#FFFFFF; border:1px solid #DCE3EC;
    box-shadow:0 1px 2px rgba(16,40,72,.06); color:var(--ink); font-weight:600; }}
.st-key-newchat .stButton > button:hover {{ border-color:var(--brand); color:var(--brand); }}
.cet-active {{ display:block; padding:9px 12px; border-radius:10px; background:var(--tint); color:var(--ink);
              font-size:14px; font-weight:600; margin:2px 0; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.cet-req {{ background:#FFFFFF; border:1px solid var(--line); border-radius:12px; padding:10px 12px; margin:6px 0; }}
.cet-req .top {{ display:flex; justify-content:space-between; align-items:center; gap:8px; }}
.cet-req .id {{ font-size:12px; font-weight:500; color:var(--ink); }}
.cet-req .acc {{ font-size:13px; color:var(--text); margin-top:4px; }}
.cet-badge {{ font-size:11px; font-weight:600; border-radius:999px; padding:3px 8px; white-space:nowrap; }}
.cet-badge.wait {{ color:#8A5300; background:#FFF3DF; }}
.cet-badge.ok {{ color:#1D6B45; background:#E5F5EC; }}
.cet-badge.info {{ color:#0B3E70; background:var(--tint); }}
.cet-empty {{ font-size:13px; color:var(--muted); padding:4px 8px; }}

/* top bar */
.cet-top {{ display:flex; flex-wrap:wrap; align-items:center; gap:12px; padding:2px 0 16px;
           border-bottom:1px solid #EEF2F6; margin-bottom:24px; }}
.cet-top h1 {{ margin:0; font-size:17px; font-weight:600; color:var(--ink); padding:0; }}
.cet-pill {{ display:inline-flex; align-items:center; gap:6px; font-size:12px; font-weight:600;
            border-radius:999px; padding:4px 10px; }}
.cet-pill.ok {{ color:#1D6B45; background:#E5F5EC; }}
.cet-pill.ok i {{ width:6px; height:6px; border-radius:50%; background:#1D8A55; display:inline-block; }}
.cet-pill.test {{ color:#8A5300; background:#FFF3DF; }}

/* welcome */
.cet-welcome {{ text-align:center; padding:56px 8px 20px; }}
.cet-welcome h2 {{ font-size:28px; font-weight:700; color:var(--ink); margin:0 0 8px; }}
.cet-welcome p {{ color:var(--muted); margin:0; font-size:15px; }}
.st-key-starters .stButton > button {{ width:100%; text-align:left; border-radius:14px; border:1px solid var(--line);
    background:#FFFFFF; color:var(--ink); padding:14px 16px; min-height:84px; box-shadow:0 1px 2px rgba(16,40,72,.05); }}
.st-key-starters .stButton > button:hover {{ border-color:var(--brand); color:var(--brand); }}
.st-key-starters .stButton > button p {{ text-align:left; white-space:normal; overflow:visible; text-overflow:clip; }}
.st-key-starters .stButton > button div {{ overflow:visible; }}

/* messages: user = blue bubble on the right, agent = plain text with its logo */
[data-testid="stChatMessage"] {{ background:transparent; padding:0; margin:0 0 26px; gap:14px; }}
[data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li {{ font-size:15px; line-height:1.65; color:var(--ink); }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) {{ justify-content:flex-end; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageAvatarUser"] {{ display:none; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stChatMessageContent"] {{
    flex:0 1 auto; width:auto; max-width:78%; margin:0 0 0 auto !important; background:var(--brand);
    border-radius:18px 18px 6px 18px; padding:11px 16px; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) [data-testid="stMarkdownContainer"],
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) .stMarkdown p {{ margin:0 !important; }}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) p,
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]) a {{ color:#FFFFFF; margin:0; }}
[data-testid="stChatMessage"] code {{ background:var(--tint); color:#0B3E70; border-radius:6px; padding:2px 6px; font-size:12.5px; }}

/* source chips, request card, ticket */
.cet-chips {{ display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin:4px 0 2px; }}
.cet-chips .lbl {{ font-size:12px; color:var(--muted); }}
.cet-chip {{ display:inline-flex; align-items:center; gap:6px; font-size:12px; color:var(--text);
            padding:5px 10px; border-radius:999px; border:1px solid #E3E9F0; background:#FFFFFF; }}
.cet-card {{ border:1px solid #E3E9F0; border-radius:16px; background:#FFFFFF; box-shadow:0 6px 20px rgba(16,40,72,.06);
            padding:18px 20px; margin:4px 0 22px; }}
.cet-card .h {{ display:flex; justify-content:space-between; align-items:baseline; gap:12px; }}
.cet-card .h b {{ font-size:15px; font-weight:600; color:var(--ink); }}
.cet-card .h span {{ font-size:13px; color:var(--muted); }}
.cet-bar {{ height:6px; border-radius:999px; background:#EDF2F7; overflow:hidden; margin:12px 0 14px; }}
.cet-bar div {{ height:100%; border-radius:999px; background:var(--brand); }}
.cet-grid {{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px 24px; font-size:13px; }}
.cet-grid > div {{ display:flex; gap:8px; align-items:center; min-width:0; }}
.cet-grid .k {{ color:var(--muted); white-space:nowrap; }}
.cet-grid .k.now {{ color:var(--ink); font-weight:600; }}
.cet-grid .v {{ margin-left:auto; color:var(--ink); font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
.cet-grid .v.q {{ color:var(--muted); font-weight:400; }}
.cet-dot {{ width:14px; height:14px; border-radius:50%; border:2px solid #C5D0DC; box-sizing:border-box; flex:none; }}
.cet-dot.now {{ border-color:var(--brand); }}
.cet-ticket {{ display:flex; align-items:center; gap:10px; background:#EEF8F2; border:1px solid #BFE3CF;
              border-radius:12px; padding:12px 16px; margin:6px 0 2px; color:#1D4D35; font-size:14px; }}
@media (max-width: 640px) {{ .cet-grid {{ grid-template-columns:minmax(0,1fr); }} }}

/* quick replies and composer */
.st-key-quick .stButton > button {{ border-radius:999px; border:1px solid #DCE3EC; background:#FFFFFF; color:var(--text);
    font-size:13px; font-weight:500; min-height:36px; padding:0 14px; }}
.st-key-quick .stButton > button:hover {{ border-color:var(--brand); color:var(--brand); }}
[data-testid="stChatInput"] {{ border-radius:20px; border:1px solid #D6DFEA; background:#FFFFFF;
    box-shadow:0 10px 30px rgba(16,40,72,.08); }}
[data-testid="stChatInput"]:focus-within {{ border-color:var(--brand); }}
/* typed text stays dark on the white box, also when the browser or OS is in dark mode */
[data-testid="stChatInput"] > div, [data-testid="stChatInput"] [data-baseweb="textarea"],
[data-testid="stChatInput"] [data-baseweb="base-input"] {{ background:#FFFFFF !important; }}
[data-testid="stChatInput"] textarea {{ color:var(--ink) !important; -webkit-text-fill-color:var(--ink) !important;
    caret-color:var(--brand) !important; background:#FFFFFF !important; }}
[data-testid="stChatInput"] textarea::placeholder {{ color:#8A97A8 !important; -webkit-text-fill-color:#8A97A8 !important; opacity:1; }}
[data-testid="stChatInputSubmitButton"] {{ background:var(--brand); border-radius:12px; }}
[data-testid="stChatInputSubmitButton"] svg {{ fill:#FFFFFF; color:#FFFFFF; }}
[data-testid="stBottomBlockContainer"] {{ background:linear-gradient(180deg, rgba(255,255,255,0), #FFFFFF 40%); }}
.cet-foot {{ text-align:center; font-size:12px; color:var(--muted); margin-top:-6px; }}
</style>
""", unsafe_allow_html=True)

DOC_ICON = ('<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#5B6878" stroke-width="2" '
            'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 '
            '1 1h12a1 1 0 0 0 1-1V8z"/><path d="M14 3v5h5"/></svg>')
TICK = ('<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#1D8A55" stroke-width="2.4" '
        'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5 9-10"/></svg>')


# ---- agent ----------------------------------------------------------------------------------
def demo_answer(question, on_token=None):
    if "tag" in question.lower():
        text = ("Every cloud account carries the five mandatory tags from the tagging standard [1]:\n\n"
                "`Technical:ApplicationID` · `Technical:ApplicationName` · `Technical:Environment` · "
                "`Technical:PlatformOwner` · `Technical:PatchWindow`")
        src = [{"note_path": "tags.md", "heading_path": "Mandatory tags (AWS, Azure and GCP)", "cited": True}]
    else:
        text = ("After you submit a request, your **manager approves it** in ServiceNow. Cloud Engineering "
                "then gets a task, a pull request is opened automatically, and **two engineers review it** "
                "before the account is created [1].")
        src = [{"note_path": "README.md", "heading_path": "Cloud account request agent (AWS / GCP)", "cited": True}]
    if on_token:
        on_token(text)
    return {"answer": text, "sources": src}


def rag_answer(question, on_token=None):
    if DEMO:
        return demo_answer(question, on_token)
    model = st.session_state.model
    return chat.ask(question, on_token=on_token,
                    chat_fn=lambda m, on_token: chat.ollama_chat(m, model=model, on_token=on_token))


def make_agent():
    return Agent(requester=st.session_state.requester.strip(), answer_fn=rag_answer,
                 extract_fn=(lambda *a: {}) if DEMO else None, servicenow=get_client(st.session_state.mode))


def new_chat():
    cid = uuid.uuid4().hex[:8]
    st.session_state.chats[cid] = {"title": "New chat", "messages": [], "agent": make_agent()}
    st.session_state.current = cid


st.session_state.setdefault("requester", config.REQUESTER_EMAIL)
st.session_state.setdefault("mode", config.SERVICENOW_MODE if config.SERVICENOW_MODE in MODES else "fake")
st.session_state.setdefault("model", config.CHAT_MODEL)
st.session_state.setdefault("chats", {})
st.session_state.setdefault("requests", [])          # tickets created in this browser session
if not st.session_state.get("current") or st.session_state.current not in st.session_state.chats:
    new_chat()
conv = st.session_state.chats[st.session_state.current]
agent = conv["agent"]


def fake_tickets(limit=5):
    """Requests saved by fake mode (data/servicenow/*.json), newest first."""
    folder = Path(config.SERVICENOW_FAKE_DIR)
    out = []
    for p in sorted(folder.glob("RITM*.json"), reverse=True)[:limit]:
        try:
            t = json.loads(p.read_text())
            v = t.get("variables", {})
            out.append({"number": t["number"], "account": v.get("account_name") or v.get("project_id", ""),
                        "status": "Saved (test)", "kind": "info"})
        except (OSError, ValueError, KeyError):
            continue
    return out


# ---- left panel -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f'<div class="cet-brand">{_logo_html(36, 10)}<div><div class="n">CET Provisioner</div>'
                f'<div class="s">Cloud Engineering Team</div></div></div>', unsafe_allow_html=True)
    with st.container(key="newchat"):
        if st.button("＋  New chat", key="new_chat"):
            new_chat()
            st.rerun()

    st.markdown('<div class="cet-label">Chats</div>', unsafe_allow_html=True)
    for cid, c in reversed(list(st.session_state.chats.items())):
        if not c["messages"] and cid != st.session_state.current:
            continue
        if cid == st.session_state.current:
            st.markdown(f'<div class="cet-active">{html.escape(c["title"])}</div>', unsafe_allow_html=True)
        elif st.button(c["title"], key=f"chat_{cid}"):
            st.session_state.current = cid
            st.rerun()

    st.markdown('<div class="cet-label">Your requests</div>', unsafe_allow_html=True)
    session_numbers = {r["number"] for r in st.session_state.requests}
    shown = list(reversed(st.session_state.requests))
    if st.session_state.mode == "fake":
        shown += [t for t in fake_tickets() if t["number"] not in session_numbers]
    if not shown:
        st.markdown('<div class="cet-empty">No requests yet.</div>', unsafe_allow_html=True)
    for r in shown[:6]:
        st.markdown(f'<div class="cet-req"><div class="top"><span class="id cet-mono">{html.escape(r["number"])}</span>'
                    f'<span class="cet-badge {r["kind"]}">{html.escape(r["status"])}</span></div>'
                    f'<div class="acc">{html.escape(r["account"])}</div></div>', unsafe_allow_html=True)

    with st.expander("Settings"):
        st.text_input("Your email", key="requester", placeholder="you@company.com",
                      help="Used as 'Requested for' on account and project requests.")
        st.selectbox("ServiceNow mode", MODES, key="mode",
                     help="fake = test ticket saved locally · dry_run = show what would be sent · live = real ServiceNow")
        st.text_input("Chat model", key="model")
        st.caption("Settings apply to new chats.")


# ---- top bar --------------------------------------------------------------------------------
mode = st.session_state.mode
pill = ('<span class="cet-pill ok"><i></i>ServiceNow connected</span>' if mode == "live"
        else f'<span class="cet-pill test">ServiceNow: {html.escape(mode)} (test)</span>')
st.markdown(f'<div class="cet-top"><h1>{html.escape(conv["title"])}</h1>{pill}</div>', unsafe_allow_html=True)


# ---- pieces ---------------------------------------------------------------------------------
def source_chips(sources):
    cited = [s for s in sources if s.get("cited")] or sources[:2]
    if cited:
        chips = "".join(f'<span class="cet-chip">{DOC_ICON}{html.escape(s["note_path"])} · '
                        f'{html.escape(s["heading_path"].split(" > ")[-1])}</span>' for s in cited)
        st.markdown(f'<div class="cet-chips"><span class="lbl">Sources</span>{chips}</div>', unsafe_allow_html=True)


def ticket_badge(ticket):
    if ticket and ticket.get("number"):
        link = (f' · <a href="{html.escape(ticket["url"])}" target="_blank">Open in ServiceNow</a>'
                if ticket.get("url") else "")
        st.markdown(f'<div class="cet-ticket">{TICK}<span>Request <b class="cet-mono">{html.escape(ticket["number"])}</b>'
                    f' created and sent for manager approval{link}</span></div>', unsafe_allow_html=True)


def request_card():
    intake = agent.intake
    if not intake or intake.finished:
        return
    fields = intake.form.fields
    done = sum(1 for f in fields if f.name in intake.values)
    rows = []
    for f in fields:
        if f.name in intake.values:
            rows.append(f'<div>{TICK}<span class="k">{html.escape(f.label)}</span>'
                        f'<span class="v">{html.escape(str(intake.values[f.name]))}</span></div>')
        elif f.name == intake.current:
            rows.append(f'<div><span class="cet-dot now"></span><span class="k now">{html.escape(f.label)}</span>'
                        f'<span class="v q">asking now</span></div>')
        else:
            rows.append(f'<div><span class="cet-dot"></span><span class="k">{html.escape(f.label)}</span>'
                        f'<span class="v q">next</span></div>')
    status = "Ready to submit" if intake.stage == "confirming" else f"{done} of {len(fields)} details"
    st.markdown(f'<div class="cet-card"><div class="h"><b>{html.escape(intake.form.title)}</b><span>{status}</span></div>'
                f'<div class="cet-bar"><div style="width:{int(100 * done / len(fields))}%"></div></div>'
                f'<div class="cet-grid">{"".join(rows)}</div></div>', unsafe_allow_html=True)


avatar = str(LOGO) if LOGO else "assistant"


def show(m):
    with st.chat_message(m["role"], avatar=avatar if m["role"] == "assistant" else "user"):
        st.markdown(m["content"])
        if m.get("sources"):
            source_chips(m["sources"])
        if m.get("ticket"):
            ticket_badge(m["ticket"])


# ---- conversation ---------------------------------------------------------------------------
prompt = st.chat_input("Message CET Provisioner…") or st.session_state.pop("pending", None)

if not conv["messages"] and not prompt:
    st.markdown('<div class="cet-welcome"><h2>How can I help today?</h2>'
                f'<p>Ask about our cloud standards, or request {html.escape(WHAT)}.</p></div>', unsafe_allow_html=True)
    with st.container(key="starters"):
        for col, (title, question) in zip(st.columns(len(STARTERS)), STARTERS):
            if col.button(f"**{title}**  \n{question}", key=f"start_{title}", use_container_width=True):
                st.session_state.pending = question
                st.rerun()

for m in conv["messages"]:
    show(m)

if prompt:
    if conv["title"] == "New chat":
        conv["title"] = prompt[:42] + ("…" if len(prompt) > 42 else "")
    conv["messages"].append({"role": "user", "content": prompt})
    show(conv["messages"][-1])
    with st.chat_message("assistant", avatar=avatar):
        box, streamed = st.empty(), []

        def on_token(t):
            streamed.append(t)
            box.markdown("".join(streamed) + "▌")

        agent.answer_fn = (lambda q: rag_answer(q)) if agent.intake else (lambda q: rag_answer(q, on_token=on_token))
        try:
            with st.spinner("Thinking…"):
                reply = agent.handle(prompt)
        except RuntimeError as e:                   # e.g. Ollama not running, model missing
            box.empty()
            st.error(str(e))
            conv["messages"].append({"role": "assistant", "content": f"⚠ {e}"})
        else:
            if reply.kind == "intake":
                text = reply.text.replace("\n", "  \n")
                ticket = reply.data.get("ticket")
                box.markdown(text)
                ticket_badge(ticket)
                conv["messages"].append({"role": "assistant", "content": text, "ticket": ticket})
                if ticket and ticket.get("number"):
                    st.session_state.requests.append({
                        "number": ticket["number"],
                        "account": (reply.data.get("values", {}).get("account_name")
                                    or (ticket.get("payload") or {}).get("variables", {}).get("project_id", "")),
                        "status": "Awaiting approval" if ticket.get("mode") == "live" else "Saved (test)",
                        "kind": "wait" if ticket.get("mode") == "live" else "info"})
            else:
                text = reply.data.get("answer", "") or "".join(streamed)
                box.markdown(text)
                source_chips(reply.data.get("sources", []))
                conv["messages"].append({"role": "assistant", "content": text,
                                         "sources": reply.data.get("sources", [])})
    st.rerun()                                       # redraw so the panel, title and card are current

request_card()

# quick replies while a request is open
if agent.intake and not agent.intake.finished:
    quick = [("Yes, submit", "yes"), ("Edit a detail", "edit"), ("Cancel request", "cancel")] \
        if agent.intake.stage == "confirming" else [("Cancel request", "cancel")]
    with st.container(key="quick"):
        for col, (label, text) in zip(st.columns([1.2] * len(quick) + [5 - len(quick)]), quick):
            if col.button(label, key=f"q_{text}"):
                st.session_state.pending = text
                st.rerun()

st.markdown('<div class="cet-foot">Answers come from approved Cloud Engineering documents. '
            'New GCP project requests need your manager\'s or account approver\'s approval in ServiceNow.</div>', unsafe_allow_html=True)
