"""Chat with the agent: ask questions about your docs, or request a new AWS account.

Run from the project root (Ollama running, index built with `python -m scripts.index`):
    python -m scripts.agent --requester you@company.com
    SERVICENOW_MODE=dry_run python -m scripts.agent       # show the payload, create nothing
    python -m scripts.agent --tickets                     # list fake tickets created so far

Try:  "I need a new AWS account for the RME team"
      "what is a ServiceNow support group?"   (answered from your documents, even mid-request)
"""
import argparse
import json
import sys

import config
from md_rag import chat
from md_rag.agent import Agent
from md_rag.servicenow import LiveServiceNow, get_client

parser = argparse.ArgumentParser(description="Docs Q&A + AWS account request agent")
parser.add_argument("--requester", default=config.REQUESTER_EMAIL, help="your email (asked if empty)")
parser.add_argument("--mode", default=config.SERVICENOW_MODE, choices=["fake", "dry_run", "live"],
                    help="where requests go (default from config.SERVICENOW_MODE)")
parser.add_argument("--model", default=config.CHAT_MODEL, help="Ollama chat model")
parser.add_argument("--tickets", action="store_true", help="list fake tickets and exit")
args = parser.parse_args()

if args.tickets:
    files = sorted(config.SERVICENOW_FAKE_DIR.glob("RITM*.json"))
    if not files:
        print("No fake tickets yet.")
    for p in files:
        t = json.loads(p.read_text())
        print(f"{t['number']}  {t['created']}  {t['short_description']}  (for {t['requested_for']})")
    sys.exit(0)


def answer(question):
    """RAG answer, streamed to the screen; returns the result dict."""
    print("Agent: ", end="", flush=True)
    result = chat.ask(question, on_token=lambda t: print(t, end="", flush=True),
                      chat_fn=lambda m, on_token: chat.ollama_chat(m, model=args.model, on_token=on_token))
    print()
    cited = [s for s in result["sources"] if s["cited"]] or result["sources"][:2]
    for s in cited:
        print(f"       source: {s['note_path']} — {s['heading_path']}")
    return result


def quiet_answer(question):
    """RAG answer used inside a request (not streamed; the intake prints it)."""
    return chat.ask(question, chat_fn=lambda m, on_token: chat.ollama_chat(m, model=args.model))


if args.mode == "live":
    missing = LiveServiceNow().check_settings()
    if missing:
        sys.exit("Live ServiceNow settings missing in .env: " + ", ".join(missing) +
                 "\nRun python -m scripts.check_servicenow after filling them in.")
agent = Agent(requester=args.requester, answer_fn=answer, servicenow=get_client(args.mode))
agent_help = quiet_answer
print(f"chat model: {args.model}   ServiceNow mode: {args.mode}   requester: {args.requester or '(will ask)'}")
print("Ask about your documents, or say e.g. 'I need a new AWS account'. Blank line quits.\n")

try:
    while (text := input("You: ").strip()):
        if agent.intake:                       # inside a request, side questions are answered quietly
            agent.answer_fn = agent_help
        reply = agent.handle(text)
        agent.answer_fn = answer
        if reply.kind == "intake":
            print("Agent: " + reply.text.replace("\n", "\n       ") + "\n")
            ticket = reply.data.get("ticket")
            if ticket and ticket.get("path"):
                print(f"       (fake ticket saved to {ticket['path']})\n")
        else:
            print()
except (KeyboardInterrupt, EOFError):
    print()
except RuntimeError as e:
    sys.exit(f"\nError: {e}")
