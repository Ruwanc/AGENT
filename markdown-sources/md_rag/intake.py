"""Step-by-step collection of a request form in a chat (the "form that talks").

    start  -> ask the first missing field
    reply  -> extract values (LLM) -> validate (code) -> keep good ones, explain bad ones
           -> ask the next missing field ... until everything required is filled
    summary -> user says yes / edit <n> / cancel
    yes    -> create the ServiceNow request -> reply with the ticket number

Who decides what:
    LLM   only pulls values out of free text (extract_fn). It can't skip a field,
          approve a value or submit anything.
    code  decides validity, the next question, and when to call ServiceNow.
    RAG   (help_fn) answers side questions such as "what is a support group?".

Every collaborator is passed in, so tests run with fakes (no Ollama, no ServiceNow).
"""
import json
import re

from config import CHAT_TEMPERATURE, EXTRACT_MODEL
from md_rag.validators import validate

YES = {"yes", "y", "yep", "yeah", "confirm", "submit", "ok", "okay", "go ahead", "looks good", "correct"}
CANCEL = {"cancel", "stop", "quit", "abort", "never mind", "nevermind", "no thanks"}
QUESTION_START = ("what", "why", "how", "which", "who", "where", "can ", "should", "is ", "are ",
                  "do ", "does ", "explain")


# ---------------------------------------------------------------- LLM extraction
def llm_extract(text, form, current, values, model=EXTRACT_MODEL):
    """Ask the chat model to pull field values out of one user message. Returns {name: value}.

    Uses Ollama structured output (format=JSON schema), so the reply is always JSON
    with only known field names. Any error returns {} and the code falls back to
    using the raw reply for the field that was asked.
    """
    import ollama
    schema = {"type": "object",
              "properties": {f.name: {"type": "string"} for f in form.fields},
              "additionalProperties": False}
    # questions only, no hints: hints contain examples ("e.g. RME-AppSupport") that a
    # small model would copy as if the user had typed them
    field_list = "\n".join(f"- {f.name} ({f.label}): {f.question}" for f in form.fields)
    asked = form.field(current).question if current else "(nothing yet)"
    messages = [
        {"role": "system", "content":
            "You extract form values from one chat message. Return JSON containing ONLY the fields "
            "the message clearly states. Copy values exactly as the user wrote them; never use "
            "example values. "
            "A value answers the question that was asked, unless the message explicitly names "
            "another field (e.g. 'the technical owner is ...'). Use each value for ONE field only. "
            "Never guess, never invent, never fill a field the message does not mention."},
        {"role": "user", "content":
            f"Form fields:\n{field_list}\n\nThe user was asked: {asked}\n\nUser message: {text}"},
    ]
    try:
        reply = ollama.chat(model=model, messages=messages, format=schema,
                            options={"temperature": min(CHAT_TEMPERATURE, 0.1)})
        data = json.loads(reply["message"]["content"] or "{}")
    except Exception:
        return {}
    names = {f.name for f in form.fields}
    return {k: v.strip() for k, v in data.items() if k in names and isinstance(v, str) and v.strip()}


# ---------------------------------------------------------------- helpers
def _norm(text):
    return re.sub(r"\s+", " ", text.strip().lower().rstrip(".!"))


def _mentioned(value, text):
    """True if the value really appears in what the user typed (guards against invented values)."""
    squash = lambda s: re.sub(r"[^a-z0-9@.]", "", s.lower())
    return squash(value) and squash(value) in squash(text)


def has_cue(field, text):
    """True if the message names this field (e.g. 'technical owner', 'budget')."""
    t = " " + re.sub(r"\s+", " ", text.lower()) + " "
    return any(c.lower() in t for c in field.cues)


def looks_like_question(text):
    t = text.strip().lower()
    return t.endswith("?") or t.startswith(QUESTION_START)


# ---------------------------------------------------------------- the intake
class Intake:
    def __init__(self, form, requester="", extract_fn=None, help_fn=None, servicenow=None):
        self.form = form
        self.extract_fn = extract_fn or llm_extract
        self.help_fn = help_fn                      # question -> answer text (RAG), optional
        self.servicenow = servicenow                # object with create_request(form, values)
        self.values = {}
        self.current = None                          # name of the field we are asking for
        self.stage = "collecting"                    # collecting | confirming | done | cancelled
        self.ticket = None
        if requester:
            for f in form.fields:
                if f.prefill == "requester":
                    ok, value, _ = validate(f, requester)
                    if ok:
                        self.values[f.name] = value

    # -------- state helpers
    @property
    def finished(self):
        return self.stage in ("done", "cancelled")

    def missing(self):
        return [f for f in self.form.fields if f.required and f.name not in self.values]

    def ask(self, name, with_hint=False):
        self.current = name
        f = self.form.field(name)
        return f.question + (f"\n  ({f.hint})" if with_hint and f.hint else "")

    def summary(self):
        lines = [f"  {n}. {f.label}: {self.values.get(f.name, '—')}" for n, f in enumerate(self.form.fields, 1)]
        return ("Here is the request:\n" + "\n".join(lines) +
                f"\n\nShall I create it and assign it to {self.form.ticket.get('assignment_group', 'the team')}?"
                "\nReply yes, edit <number> (e.g. edit 3), or cancel.")

    def _next_step(self):
        """Ask the next missing field, or show the summary when everything is filled."""
        todo = self.missing()
        if todo:
            return self.ask(todo[0].name)
        self.stage, self.current = "confirming", None
        return self.summary()

    # -------- public API
    def start(self, first_message=""):
        intro = (f"Let's set up your {self.form.title}. I need {len(self.missing())} "
                 "details; you can type cancel at any time.")
        got = self._apply(first_message, use_raw=False)[0] if first_message else []
        noted = ("\nFrom your message I noted: " + ", ".join(got) + ".") if got else ""
        return f"{intro}{noted}\n\n{self._next_step()}"

    def handle(self, text):
        text = text.strip()
        if self.finished:
            return "This request is already closed. Start a new one if you need another account."
        if _norm(text) in CANCEL:
            self.stage = "cancelled"
            return "Cancelled. Nothing was sent to ServiceNow."
        if self.stage == "confirming":
            return self._handle_confirm(text)
        if looks_like_question(text) and self.help_fn:
            answer = self.help_fn(text)
            return f"{answer}\n\nBack to the request: {self.ask(self.current, with_hint=True)}"
        got, errors = self._apply(text, use_raw=True)
        parts = []
        if got:
            parts.append("Got it: " + ", ".join(got) + ".")
        parts += errors
        if errors and self.current and self.current not in self.values:
            parts.append(self.ask(self.current, with_hint=True))
        else:
            parts.append(self._next_step())
        return "\n".join(parts)

    # -------- internals
    def _apply(self, text, use_raw):
        """Extract + validate values from one message. Returns (accepted labels, error messages)."""
        found = self.extract_fn(text, self.form, self.current, dict(self.values)) or {}
        # A value is kept only if the user really typed it (_mentioned). Small models
        # sometimes return an example from the hint instead (e.g. "RME-AppSupport" when the
        # user typed "Cloud Engineering"); that value is dropped and the raw reply is used.
        # A field other than the one just asked also needs a cue word in the message.
        # Without this, "ruwan@x.com" would fill every email field and "ruwan" Account Name.
        candidates = {k: v for k, v in found.items()
                      if _mentioned(v, text)
                      and (k == self.current or has_cue(self.form.field(k), text))}
        others_given = any(k != self.current for k in candidates)
        if use_raw and self.current and self.current not in candidates and not others_given:
            candidates[self.current] = text          # the reply IS the answer to the question asked
        got, errors = [], []
        for name, raw in candidates.items():
            f = self.form.field(name)
            ok, value, error = validate(f, raw)
            if ok:
                self.values[name] = value
                got.append(f"{f.label} = {value}")
            else:
                errors.append(f"⚠ {error}")
                if name != self.current:
                    self.values.pop(name, None)
        return got, errors

    def _handle_confirm(self, text):
        t = _norm(text)
        if t in YES:
            return self._submit()
        m = re.match(r"^(?:edit|change|fix)?\s*(\d+)$", t)
        if m or t in ("edit", "change"):
            n = int(m.group(1)) if m else 0
            if 1 <= n <= len(self.form.fields):
                self.stage = "collecting"
                f = self.form.fields[n - 1]
                self.values.pop(f.name, None)
                return f"OK, let's change {f.label} (now empty).\n{self.ask(f.name, with_hint=True)}"
            return "Which one? Reply edit <number> using the numbers in the summary."
        # "change the technical owner to x@y.com": take any values the message states
        self.current = None
        got, errors = self._apply(text, use_raw=False)
        if got or errors:
            return "\n".join((["Updated: " + ", ".join(got) + "."] if got else []) + errors +
                             ["", self._next_step()])
        return "Please reply yes to submit, edit <number> to change a value, or cancel."

    def _submit(self):
        if self.servicenow is None:
            return "No ServiceNow client is configured, so nothing was sent."
        try:
            self.ticket = self.servicenow.create_request(self.form, dict(self.values))
        except Exception as e:                       # keep the draft so the user can retry
            return f"⚠ The request could not be created: {e}\nYour answers are kept. Reply yes to try again, or cancel."
        self.stage = "done"
        if self.ticket.get("mode") == "dry_run":
            return ("Dry run: nothing was created. This is what would be sent:\n" +
                    json.dumps(self.ticket["payload"], indent=2))
        link = f"\nTrack it here: {self.ticket['url']}" if self.ticket.get("url") else ""
        return (f"Done. Request {self.ticket['number']} was created on behalf of "
                f"{self.values.get('requested_for', 'you')} and assigned to "
                f"{self.form.ticket.get('assignment_group', 'the team')}.{link}")
