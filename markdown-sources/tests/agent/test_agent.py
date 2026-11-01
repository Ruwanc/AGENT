"""AWS account request agent: validators, intake conversation, routing, fake ServiceNow.
No Ollama and no ServiceNow needed: extraction and RAG answers are faked."""
import json
import re

import pytest

import config
from cet_agent.agent.router import Agent, wants_aws_account
from cet_agent.agent.forms import load_form
from cet_agent.agent.intake import Intake
from cet_agent.integrations.servicenow import DryRunServiceNow, FakeServiceNow, LiveServiceNow, build_payload
from cet_agent.agent.validators import validate

FORM = load_form(config.ACCOUNT_FORM)
F = FORM.field
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")


def no_extract(text, form, current, values):
    return {}


def simple_extract(text, form, current, values):
    """Tiny stand-in for the LLM: finds 'owner X', 'approver X', 'name X' and emails."""
    out = {}
    m = re.search(r"technical owner (?:is )?(\S+@\S+)", text, re.I)
    if m:
        out["technical_owner"] = m.group(1)
    m = re.search(r"approver (?:is )?(\S+@\S+)", text, re.I)
    if m:
        out["budget_approver"] = m.group(1)
    m = re.search(r"(?:called|named) ([\w-]+)", text, re.I)
    if m:
        out["account_name"] = m.group(1)
    m = re.search(r"for the (\w+) team", text, re.I)
    if m:
        out["app_team_name"] = m.group(1)
    return out


def hallucinating_extract(text, form, current, values):
    return {"budget_approver": "invented.person@corp.com"}


# ---------------------------------------------------------------- form + validators
def test_form_has_the_requested_fields_in_order():
    assert [f.label for f in FORM.fields] == ["Requested for", "Account Name", "App/Team name",
                                             "ServiceNow support group", "Technical Owner", "Budget Approver"]


@pytest.mark.parametrize("raw,ok,value", [
    ("rme-orders-nonprod", True, "rme-orders-nonprod"),
    ("RME Orders NonProd", True, "rme-orders-nonprod"),   # normalised to a slug
    ("ab", False, "ab"),                                   # too short
    ("test", False, "test"),                               # too generic
    ("9lives", False, "9lives"),                           # must start with a letter
    ("x" * 41, False, "x" * 41),                           # too long
])
def test_account_name_rules(raw, ok, value):
    assert validate(F("account_name"), raw)[:2] == (ok, value)


@pytest.mark.parametrize("raw,ok", [
    ("Jane.Doe@Corp.com", True),
    ("it's jane.doe@corp.com", True),
    ("jane.doe@corp.com and mike@corp.com", False),        # only one
    ("jane at corp dot com", False),
])
def test_technical_owner_email(raw, ok):
    good, value, error = validate(F("technical_owner"), raw)
    assert good is ok
    if ok:
        assert value == "jane.doe@corp.com"
    else:
        assert error


@pytest.mark.parametrize("raw,ok", [
    ("kurt.brochu@corp.com", True),
    ("rme-team@corp.com", False),
    ("cloud.support@corp.com", False),
    ("dl-finance@corp.com", False),
])
def test_budget_approver_must_be_a_person(raw, ok):
    assert validate(F("budget_approver"), raw)[0] is ok


def test_allowed_domains():
    assert validate(F("technical_owner"), "a@corp.com", allowed_domains=["corp.com"])[0]
    assert not validate(F("technical_owner"), "a@gmail.com", allowed_domains=["corp.com"])[0]


# ---------------------------------------------------------------- the conversation
def run(intake, *messages):
    return [intake.handle(m) for m in messages]


def test_full_happy_path_creates_a_fake_ticket(tmp_path):
    sn = FakeServiceNow(tmp_path)
    intake = Intake(FORM, requester="ruwan@corp.com", extract_fn=no_extract, servicenow=sn)
    first = intake.start()
    assert "Account Name" not in first and FORM.field("account_name").question in first
    replies = run(intake, "rme-orders-nonprod", "RME", "RME-AppSupport",
                  "jane.doe@corp.com", "kurt.brochu@corp.com")
    assert "Here is the request" in replies[-1] and intake.stage == "confirming"
    done = intake.handle("yes")
    assert "RITM0010001" in done and intake.stage == "done"
    saved = json.loads((tmp_path / "RITM0010001.json").read_text())
    assert saved["requested_for"] == "ruwan@corp.com"
    assert saved["assignment_group"] == "Cloud Engineering"
    assert saved["short_description"] == "New AWS account: rme-orders-nonprod"
    assert saved["variables"]["technical_owner"] == "jane.doe@corp.com"


def test_requester_is_asked_when_unknown(tmp_path):
    intake = Intake(FORM, extract_fn=no_extract, servicenow=FakeServiceNow(tmp_path))
    assert FORM.field("requested_for").question in intake.start()


def test_invalid_answer_is_explained_and_asked_again(tmp_path):
    intake = Intake(FORM, requester="r@corp.com", extract_fn=no_extract, servicenow=FakeServiceNow(tmp_path))
    intake.start()
    r = intake.handle("test")
    assert "too generic" in r and intake.current == "account_name" and "account_name" not in intake.values
    r = intake.handle("rme-orders")
    assert "Account Name = rme-orders" in r and intake.current == "app_team_name"


def test_two_emails_for_one_owner_is_rejected(tmp_path):
    intake = Intake(FORM, requester="r@corp.com", extract_fn=no_extract, servicenow=FakeServiceNow(tmp_path))
    intake.start()
    run(intake, "rme-orders", "RME", "RME-AppSupport")
    r = intake.handle("adlm@corp.com and mike@corp.com")
    assert "only one email" in r and intake.current == "technical_owner"


def test_one_message_can_fill_several_fields(tmp_path):
    intake = Intake(FORM, requester="r@corp.com", extract_fn=simple_extract, servicenow=FakeServiceNow(tmp_path))
    start = intake.start("I need an AWS account called rme-orders for the RME team")
    assert "Account Name = rme-orders" in start and "App/Team name = RME" in start
    assert intake.current == "support_group"


def test_invented_values_are_ignored(tmp_path):
    intake = Intake(FORM, requester="r@corp.com", extract_fn=hallucinating_extract,
                    servicenow=FakeServiceNow(tmp_path))
    intake.start()
    intake.handle("rme-orders")
    assert "budget_approver" not in intake.values          # not in the user's text -> rejected
    assert intake.values["account_name"] == "rme-orders"


def test_side_question_is_answered_with_rag_and_the_question_repeated(tmp_path):
    asked = []
    intake = Intake(FORM, requester="r@corp.com", extract_fn=no_extract, servicenow=FakeServiceNow(tmp_path),
                    help_fn=lambda q: asked.append(q) or "A support group handles incidents [1].")
    intake.start()
    r = intake.handle("what should the account name look like?")
    assert asked and "handles incidents" in r and FORM.field("account_name").question in r
    assert "account_name" not in intake.values


def test_edit_from_summary_then_submit(tmp_path):
    intake = Intake(FORM, requester="r@corp.com", extract_fn=no_extract, servicenow=FakeServiceNow(tmp_path))
    intake.start()
    run(intake, "rme-orders", "RME", "RME-AppSupport", "jane@corp.com", "kurt@corp.com")
    r = intake.handle("edit 5")
    assert "Technical Owner" in r and intake.current == "technical_owner"
    r = intake.handle("mike@corp.com")
    assert "Here is the request" in r and "mike@corp.com" in r
    assert "RITM" in intake.handle("yes")


def test_change_value_in_words_at_summary(tmp_path):
    intake = Intake(FORM, requester="r@corp.com", extract_fn=simple_extract, servicenow=FakeServiceNow(tmp_path))
    intake.start()
    run(intake, "rme-orders", "RME", "RME-AppSupport", "jane@corp.com", "kurt@corp.com")
    r = intake.handle("change it, the technical owner is mike@corp.com")
    assert "Updated: Technical Owner = mike@corp.com" in r and intake.stage == "confirming"


def test_cancel_sends_nothing(tmp_path):
    intake = Intake(FORM, requester="r@corp.com", extract_fn=no_extract, servicenow=FakeServiceNow(tmp_path))
    intake.start()
    intake.handle("rme-orders")
    assert "Nothing was sent" in intake.handle("cancel")
    assert intake.finished and not list(tmp_path.glob("*.json"))


def test_servicenow_error_keeps_the_draft(tmp_path):
    intake = Intake(FORM, requester="r@corp.com", extract_fn=no_extract, servicenow=LiveServiceNow())
    intake.start()
    run(intake, "rme-orders", "RME", "RME-AppSupport", "jane@corp.com", "kurt@corp.com")
    r = intake.handle("yes")
    assert "could not be created" in r and intake.stage == "confirming"
    intake.servicenow = FakeServiceNow(tmp_path)
    assert "RITM" in intake.handle("yes")


def test_dry_run_creates_nothing_and_shows_payload(tmp_path):
    intake = Intake(FORM, requester="r@corp.com", extract_fn=no_extract, servicenow=DryRunServiceNow())
    intake.start()
    run(intake, "rme-orders", "RME", "RME-AppSupport", "jane@corp.com", "kurt@corp.com")
    r = intake.handle("yes")
    assert "Dry run" in r and '"assignment_group": "Cloud Engineering"' in r


def test_fake_ticket_numbers_increase(tmp_path):
    sn = FakeServiceNow(tmp_path)
    values = {"requested_for": "r@corp.com", "account_name": "a-b", "app_team_name": "X",
              "support_group": "G", "technical_owner": "t@corp.com", "budget_approver": "b@corp.com"}
    assert [sn.create_request(FORM, values)["number"] for _ in range(3)] == \
           ["RITM0010001", "RITM0010002", "RITM0010003"]
    assert build_payload(FORM, values)["variables"]["support_group"] == "G"


# ---------------------------------------------------------------- routing
@pytest.mark.parametrize("text,expected", [
    ("I need a new AWS account", True),
    ("can you create an aws account for the RME team?", True),
    ("Please raise a request for an Amazon Web Services account", True),
    ("How many AWS accounts do we have?", False),
    ("What is a patch window?", False),
    ("I need a new Azure subscription", False),
])
def test_router(text, expected):
    assert wants_aws_account(text) is expected


def test_agent_routes_questions_to_rag_and_requests_to_intake(tmp_path):
    asked = []
    agent = Agent(form=FORM, requester="r@corp.com", extract_fn=no_extract,
                  answer_fn=lambda q: asked.append(q) or {"answer": "From the docs [1]."},
                  servicenow=FakeServiceNow(tmp_path))
    assert agent.handle("what is a patch window?").kind == "answer" and asked
    r = agent.handle("I need a new AWS account")
    assert r.kind == "intake" and agent.intake is not None
    for msg in ("rme-orders", "RME", "RME-AppSupport", "jane@corp.com", "kurt@corp.com", "yes"):
        r = agent.handle(msg)
    assert r.data["ticket"]["number"] == "RITM0010001" and agent.intake is None
    assert agent.handle("thanks, what is a support group?").kind == "answer"


# ---------------------------------------------------------------- over-eager extraction (real bug)
def greedy_extract(text, form, current, values):
    """What llama3.2:3b actually returned for the reply 'ruwan@gmail.com'."""
    if "@" in text:
        return {"requested_for": text, "account_name": text.split("@")[0],
                "technical_owner": text, "budget_approver": text}
    return {"account_name": "new aws account"}


def test_one_email_reply_fills_only_the_field_asked(tmp_path):
    intake = Intake(FORM, extract_fn=greedy_extract, servicenow=FakeServiceNow(tmp_path))
    intake.start("I need a new AWS account")
    assert intake.values == {}                                   # "new aws account" is not a name
    r = intake.handle("ruwan@gmail.com")
    assert intake.values == {"requested_for": "ruwan@gmail.com"}
    assert r.startswith("Got it: Requested for = ruwan@gmail.com.")
    assert intake.current == "account_name"


def test_other_fields_need_a_cue_word(tmp_path):
    intake = Intake(FORM, requester="r@corp.com", extract_fn=greedy_extract,
                    servicenow=FakeServiceNow(tmp_path))
    intake.start()
    run(intake, "rme-orders", "RME", "RME-AppSupport")
    intake.handle("jane@corp.com")                               # asked: technical owner
    assert intake.values["technical_owner"] == "jane@corp.com"
    assert "budget_approver" not in intake.values                # not named -> asked next
    assert intake.current == "budget_approver"


def test_example_from_hint_is_not_used_instead_of_the_reply(tmp_path):
    """Bug report: user typed 'Cloud Engineering', the model returned the hint's example."""
    copy_hint = lambda text, form, current, values: {"support_group": "RME-AppSupport"}
    intake = Intake(FORM, requester="ruwan@corp.com", extract_fn=copy_hint,
                    servicenow=FakeServiceNow(tmp_path))
    intake.start()
    intake.values.update({"account_name": "rme-orders-nonprod", "app_team_name": "RME"})
    intake.current = "support_group"
    reply = intake.handle("Cloud Engineering")
    assert intake.values["support_group"] == "Cloud Engineering"
    assert "RME-AppSupport" not in reply


def test_extracted_value_for_asked_field_is_kept_when_typed(tmp_path):
    """The extractor may still pick the value out of a longer sentence."""
    pick = lambda text, form, current, values: {"support_group": "Cloud Engineering"}
    intake = Intake(FORM, requester="ruwan@corp.com", extract_fn=pick, servicenow=FakeServiceNow(tmp_path))
    intake.start()
    intake.current = "support_group"
    intake.handle("it will be supported by Cloud Engineering please")
    assert intake.values["support_group"] == "Cloud Engineering"
