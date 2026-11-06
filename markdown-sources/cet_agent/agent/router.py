"""The agent: one chat that either answers questions (RAG) or runs a cloud account request.

    message ──► request open? ──yes──► Intake.handle(message)
                    │ no
                    ▼
            wants an AWS account / GCP project? ──yes──► start a new Intake for that cloud
                    │ no              (only clouds in ENABLED_CLOUDS; others get a polite "not available")
                    ▼
            "a new cloud account" and 2+ clouds on? ──yes──► ask "AWS or GCP?"
                    │ no
                    ▼
            RAG answer (chat.ask)

The router is plain keyword matching on purpose: it is predictable, instant and easy to
test. A request stays open until it is submitted or cancelled; questions asked during the
request are answered with RAG without losing the answers already given. Someone who wants
both an AWS account and a GCP project gets them one after the other (two RITMs).
"""
import re
from dataclasses import dataclass, field

import config
from cet_agent.agent.forms import load_form
from cet_agent.agent.intake import CANCEL, YES, Intake, _norm, looks_like_question

VERBS = r"(need|want|request|create|new|open|get|set ?up|provision|raise|order|apply)"

# Words that name each cloud and what a "request" is called there. Add Azure here later.
CLOUDS = {
    "aws": {"label": "AWS account", "names": r"(aws|amazon web services)",
            "things": r"accounts?"},
    "gcp": {"label": "GCP project", "names": r"(gcp|google cloud(?: platform)?)",
            "things": r"(projects?|accounts?)"},
}


def parse_enabled(raw):
    """'aws,gcp' -> ['aws', 'gcp']. Unknown names stop the agent with a clear message."""
    items = raw if isinstance(raw, (list, tuple)) else str(raw).split(",")
    clouds = []
    for c in (str(x).strip().lower() for x in items):
        if not c or c in clouds:
            continue
        if c not in CLOUDS or c not in config.CLOUD_FORMS:
            raise ValueError(f"ENABLED_CLOUDS: unknown cloud {c!r}; use {', '.join(CLOUDS)} "
                             f"or a comma-separated mix such as aws,gcp")
        clouds.append(c)
    if not clouds:
        raise ValueError("ENABLED_CLOUDS is empty; set it to aws, gcp or aws,gcp")
    return clouds


def requested_clouds(text):
    """Clouds the message asks to create, in the order they are mentioned.
    'I need an AWS account and a GCP project' -> ['aws', 'gcp']."""
    t = text.lower()
    if not re.search(rf"\b{VERBS}\b", t):
        return []
    found = []
    for key, c in CLOUDS.items():
        m = re.search(rf"\b{c['names']}\b", t)
        if m and re.search(rf"\b{c['things']}\b", t):
            found.append((m.start(), key))
    return [key for _, key in sorted(found)]


def wants_aws_account(text):
    """True for 'I need an AWS account', 'create a new aws account for RME', ..."""
    return "aws" in requested_clouds(text)


def wants_some_cloud(text):
    """'I need a new cloud account' / 'request a cloud project': a request, cloud not named."""
    t = text.lower()
    return bool(re.search(rf"\b{VERBS}\b", t) and re.search(r"\bcloud\b", t)
                and re.search(r"\b(accounts?|projects?|subscriptions?)\b", t))


def _labels(clouds):
    names = [CLOUDS[c]["label"] for c in clouds]
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " or " + names[-1]


@dataclass
class Reply:
    kind: str                      # "answer" (RAG) | "intake" (account request)
    text: str = ""
    data: dict = field(default_factory=dict)


class Agent:
    def __init__(self, form=None, requester=config.REQUESTER_EMAIL, answer_fn=None,
                 extract_fn=None, servicenow=None, clouds=None, forms=None):
        if forms is not None:                       # {"aws": Form, "gcp": Form} (tests)
            self.forms = dict(forms)
        elif form is not None:                      # one form, as before GCP was added
            self.forms = {"aws": form}
        else:
            enabled = parse_enabled(config.ENABLED_CLOUDS if clouds is None else clouds)
            self.forms = {c: load_form(config.CLOUD_FORMS[c]) for c in enabled}
        self.form = next(iter(self.forms.values()))
        self.requester = requester
        self.answer_fn = answer_fn          # question -> {"answer": ..., "sources": ...}
        self.extract_fn = extract_fn
        if servicenow is None:
            from cet_agent.integrations.servicenow import get_client
            servicenow = get_client()
        self.servicenow = servicenow
        self.intake = None
        self.cloud = None                   # cloud of the open request
        self.choosing = False               # waiting for "AWS or GCP?"
        self.queued = []                    # second cloud asked for in the same message
        self.offer = None                   # cloud offered after a request finished ("yes" starts it)

    @property
    def clouds(self):
        return list(self.forms)

    def _help(self, question):
        if not self.answer_fn:
            return "(I can't look that up right now.)"
        return self.answer_fn(question).get("answer", "")

    def _start(self, cloud, text="", prefix=""):
        self.cloud, self.choosing, self.offer = cloud, False, None
        self.intake = Intake(self.forms[cloud], requester=self.requester, extract_fn=self.extract_fn,
                             help_fn=self._help, servicenow=self.servicenow)
        reply = self.intake.start(first_message=text)
        return Reply("intake", prefix + reply,
                     {"stage": self.intake.stage, "values": dict(self.intake.values), "cloud": cloud})

    def _choice_question(self):
        opts = "\n".join(f"  {n}. {CLOUDS[c]['label']}" for n, c in enumerate(self.clouds, 1))
        return f"Which one do you need?\n{opts}\nReply with the number or the name, or cancel."

    def _parse_choice(self, text):
        t = _norm(text)
        for n, c in enumerate(self.clouds, 1):
            if t == str(n) or re.search(rf"\b{CLOUDS[c]['names']}\b", t):
                return c
        return None

    def handle(self, text):
        if self.intake and not self.intake.finished:
            reply = self.intake.handle(text)
            data = {"stage": self.intake.stage, "values": dict(self.intake.values),
                    "ticket": self.intake.ticket, "cloud": self.cloud}
            if self.intake.finished:
                if self.intake.values.get("requested_for"):
                    self.requester = self.intake.values["requested_for"]   # remember for next time
                if self.intake.stage == "done" and self.queued:
                    self.offer = self.queued.pop(0)
                    reply += (f"\n\nYou also asked for a {CLOUDS[self.offer]['label']}. "
                              "Shall I start that request now? Reply yes, or ask me anything else.")
                else:
                    self.queued = []
                self.intake = None
            return Reply("intake", reply, data)

        if self.offer:                                  # "Shall I start the GCP project now?"
            cloud, self.offer = self.offer, None
            if _norm(text) in YES:
                return self._start(cloud)

        if self.choosing:                               # "AWS account or GCP project?"
            cloud = self._parse_choice(text)
            if cloud:
                return self._start(cloud)
            if _norm(text) in CANCEL:
                self.choosing = False
                return Reply("intake", "OK, no request started.", {"stage": "cancelled"})
            if not (looks_like_question(text) or requested_clouds(text)):
                return Reply("intake", "Sorry, I didn't catch that. " + self._choice_question(),
                             {"stage": "choosing"})
            self.choosing = False                       # a question or a new request: handle it below

        wanted = requested_clouds(text)
        if wanted:
            on = [c for c in wanted if c in self.forms]
            off = [c for c in wanted if c not in self.forms]
            if not on:
                msg = (f"{_labels(off)} requests aren't available here yet. "
                       f"I can take {_labels(self.clouds)} requests.")
                return Reply("answer", msg, {"answer": msg, "sources": []})   # UI shows data["answer"]
            prefix = ""
            if off:
                prefix += f"{_labels(off)} requests aren't available here yet, so this is only the {_labels(on[:1])}.\n\n"
            if len(on) > 1:
                prefix += (f"I'll do these one at a time: the {CLOUDS[on[0]]['label']} first, "
                           f"then the {_labels(on[1:])}.\n\n")
            self.queued = on[1:]
            return self._start(on[0], text, prefix)

        if len(self.forms) > 1 and wants_some_cloud(text):
            self.choosing = True
            return Reply("intake", "I can raise either request. " + self._choice_question(),
                         {"stage": "choosing"})

        if not self.answer_fn:
            return Reply("answer", f"I can only take {_labels(self.clouds)} requests right now.")
        return Reply("answer", "", self.answer_fn(text))
