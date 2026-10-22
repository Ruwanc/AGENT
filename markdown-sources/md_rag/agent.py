"""The agent: one chat that either answers questions (RAG) or runs an AWS account request.

    message ──► request open? ──yes──► Intake.handle(message)
                    │ no
                    ▼
            wants an AWS account? ──yes──► start a new Intake
                    │ no
                    ▼
            RAG answer (chat.ask)

The router is plain keyword matching on purpose: it is predictable, instant and easy to
test. A request stays open until it is submitted or cancelled; questions asked during the
request are answered with RAG without losing the answers already given.
"""
import re
from dataclasses import dataclass, field

import config
from md_rag.forms import load_form
from md_rag.intake import Intake

VERBS = r"(need|want|request|create|new|open|get|set ?up|provision|raise|order|apply)"
CLOUD = r"(aws|amazon web services)"


def wants_aws_account(text):
    """True for 'I need an AWS account', 'create a new aws account for RME', ..."""
    t = text.lower()
    return bool(re.search(rf"\b{CLOUD}\b", t) and re.search(r"\baccounts?\b", t)
                and re.search(rf"\b{VERBS}\b", t))


@dataclass
class Reply:
    kind: str                      # "answer" (RAG) | "intake" (account request)
    text: str = ""
    data: dict = field(default_factory=dict)


class Agent:
    def __init__(self, form=None, requester=config.REQUESTER_EMAIL, answer_fn=None,
                 extract_fn=None, servicenow=None):
        self.form = form or load_form(config.ACCOUNT_FORM)
        self.requester = requester
        self.answer_fn = answer_fn          # question -> {"answer": ..., "sources": ...}
        self.extract_fn = extract_fn
        if servicenow is None:
            from md_rag.servicenow import get_client
            servicenow = get_client()
        self.servicenow = servicenow
        self.intake = None

    def _help(self, question):
        if not self.answer_fn:
            return "(I can't look that up right now.)"
        return self.answer_fn(question).get("answer", "")

    def handle(self, text):
        if self.intake and not self.intake.finished:
            reply = self.intake.handle(text)
            data = {"stage": self.intake.stage, "values": dict(self.intake.values),
                    "ticket": self.intake.ticket}
            if self.intake.finished:
                if self.intake.values.get("requested_for"):
                    self.requester = self.intake.values["requested_for"]   # remember for next time
                self.intake = None
            return Reply("intake", reply, data)

        if wants_aws_account(text):
            self.intake = Intake(self.form, requester=self.requester, extract_fn=self.extract_fn,
                                 help_fn=self._help, servicenow=self.servicenow)
            reply = self.intake.start(first_message=text)
            return Reply("intake", reply, {"stage": self.intake.stage, "values": dict(self.intake.values)})

        if not self.answer_fn:
            return Reply("answer", "I can only take AWS account requests right now.")
        return Reply("answer", "", self.answer_fn(text))
