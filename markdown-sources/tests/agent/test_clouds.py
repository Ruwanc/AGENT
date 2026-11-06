"""AWS / GCP switch (ENABLED_CLOUDS), the GCP project form and its derived project ID.
No Ollama and no ServiceNow needed."""
import json
import os
import re

import pytest

import config
from cet_agent.agent.forms import load_form
from cet_agent.agent.intake import Intake
from cet_agent.agent.router import Agent, parse_enabled, requested_clouds, wants_some_cloud
from cet_agent.agent.validators import validate
from cet_agent.integrations.servicenow import FakeServiceNow, build_payload

AWS = load_form(config.CLOUD_FORMS["aws"])
GCP = load_form(config.CLOUD_FORMS["gcp"])
GCP_ID = re.compile(r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")      # Google's project ID rule
ANSWERS = ("RME", "RME-AppSupport", "jane.doe@corp.com", "kurt.brochu@corp.com")


def no_extract(text, form, current, values):
    return {}


def agent(tmp_path, clouds, answer=None):
    return Agent(requester="ruwan@corp.com", extract_fn=no_extract, clouds=clouds,
                 answer_fn=answer or (lambda q: {"answer": "From the docs [1]."}),
                 servicenow=FakeServiceNow(tmp_path))


# ---------------------------------------------------------------- the switch
@pytest.mark.parametrize("raw,expected", [
    ("aws", ["aws"]), ("gcp", ["gcp"]), ("aws,gcp", ["aws", "gcp"]),
    (" GCP , aws ", ["gcp", "aws"]), ("aws,aws", ["aws"]), (["gcp"], ["gcp"]),
])
def test_parse_enabled(raw, expected):
    assert parse_enabled(raw) == expected


@pytest.mark.parametrize("raw", ["azure", "aws,azure", "", " , "])
def test_parse_enabled_rejects_unknown_or_empty(raw):
    with pytest.raises(ValueError, match="ENABLED_CLOUDS"):
        parse_enabled(raw)


def test_default_is_aws_only():
    # nothing set in the environment or .env -> AWS only, exactly as before GCP was added
    assert os.environ.get("ENABLED_CLOUDS") or parse_enabled(config.ENABLED_CLOUDS) == ["aws"]
    a = Agent(form=AWS, servicenow=object())                 # old single-form use still works
    assert a.clouds == ["aws"] and a.form is AWS


# ---------------------------------------------------------------- recognising requests
@pytest.mark.parametrize("text,expected", [
    ("I need a new AWS account", ["aws"]),
    ("I need a new GCP project", ["gcp"]),
    ("please create a google cloud project for RME", ["gcp"]),
    ("can I get a Google Cloud Platform account?", ["gcp"]),
    ("I need an AWS account and a GCP project", ["aws", "gcp"]),
    ("I need a GCP project and an AWS account", ["gcp", "aws"]),
    ("How many GCP projects do we have?", []),
    ("What are the GCP label rules?", []),
    ("I need a new Azure subscription", []),
])
def test_requested_clouds(text, expected):
    assert requested_clouds(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("I need a new cloud account", True), ("request a cloud project please", True),
    ("I need a new AWS account", False), ("what is cloud governance?", False),
])
def test_wants_some_cloud(text, expected):
    assert (wants_some_cloud(text) and not requested_clouds(text)) is expected


# ---------------------------------------------------------------- GCP form
def test_gcp_form_has_the_aws_fields_with_project_name():
    assert [f.label for f in GCP.fields] == ["Requested for", "Project Name", "App/Team name",
                                            "ServiceNow support group", "Technical Owner", "Budget Approver"]
    assert [d.name for d in GCP.derived] == ["project_id"] and AWS.derived == []


@pytest.mark.parametrize("raw,ok,value", [
    ("rme-orders-nonprod", True, "rme-orders-nonprod"),
    ("RME Orders NonProd", True, "rme-orders-nonprod"),
    ("abc", True, "abc"),
    ("x" * 26, True, "x" * 26),
    ("x" * 27, False, "x" * 27),                   # syy- + 27 would pass Google's 30 limit
    ("ab", False, "ab"),
    ("9lives", False, "9lives"),
    ("test", False, "test"),
    ("syy-payments", False, "syy-payments"),       # the prefix is added for you
    ("my-google-app", False, "my-google-app"),     # Google doesn't allow "google" in IDs
    ("ssl-gateway", False, "ssl-gateway"),
])
def test_project_name_rules(raw, ok, value):
    good, cleaned, _ = validate(GCP.field("project_name"), raw)
    assert (good, cleaned) == (ok, value)
    if good:
        assert GCP_ID.match(GCP.derive({"project_name": cleaned})["project_id"])


def test_project_id_is_made_from_the_name():
    assert GCP.derive({"project_name": "payments-api"}) == {"project_id": "syy-payments-api"}
    assert GCP.derive({}) == {}                    # not answered yet: nothing derived


def test_gcp_happy_path_creates_a_fake_ticket(tmp_path):
    sn = FakeServiceNow(tmp_path)
    intake = Intake(GCP, requester="ruwan@corp.com", extract_fn=no_extract, servicenow=sn)
    assert "syy-" in intake.start()
    replies = [intake.handle(m) for m in ("Payments API", *ANSWERS)]
    assert "Project ID: syy-payments-api (made automatically)" in replies[-1]
    assert "RITM0010001" in intake.handle("yes")
    saved = json.loads((tmp_path / "RITM0010001.json").read_text())
    assert saved["short_description"] == "New GCP project: syy-payments-api"
    assert saved["variables"]["project_name"] == "payments-api"
    assert saved["variables"]["project_id"] == "syy-payments-api"
    assert saved["variables"]["cloud_provider"] == "gcp"
    assert "account_name" not in saved["variables"]


def test_editing_the_name_changes_the_project_id(tmp_path):
    intake = Intake(GCP, requester="ruwan@corp.com", extract_fn=no_extract,
                    servicenow=FakeServiceNow(tmp_path))
    intake.start()
    for m in ("payments-api", *ANSWERS):
        intake.handle(m)
    intake.handle("edit 2")
    assert "syy-orders-api" in intake.handle("orders-api")


def test_aws_payload_is_unchanged():
    values = {"requested_for": "r@corp.com", "account_name": "rme-orders", "app_team_name": "RME",
              "support_group": "G", "technical_owner": "t@corp.com", "budget_approver": "b@corp.com"}
    assert build_payload(AWS, values)["variables"] == {
        "account_name": "rme-orders", "app_team_name": "RME", "support_group": "G",
        "technical_owner": "t@corp.com", "budget_approver": "b@corp.com"}


# ---------------------------------------------------------------- agent with each setting
def test_aws_only_declines_gcp(tmp_path):
    a = agent(tmp_path, "aws")
    r = a.handle("I need a new GCP project")
    assert r.kind == "answer" and "GCP project requests aren't available" in r.text and a.intake is None
    assert r.data["answer"] == r.text                        # the UI shows data["answer"]
    assert a.handle("I need a new AWS account").data["cloud"] == "aws"


def test_aws_only_generic_request_still_goes_to_rag(tmp_path):
    asked = []
    a = agent(tmp_path, "aws", answer=lambda q: asked.append(q) or {"answer": "docs"})
    assert a.handle("I need a new cloud account").kind == "answer" and asked


def test_gcp_only_declines_aws_and_runs_gcp(tmp_path):
    a = agent(tmp_path, "gcp")
    assert "AWS account requests aren't available" in a.handle("I need an AWS account").text
    r = a.handle("I need a GCP project")
    assert r.kind == "intake" and r.data["cloud"] == "gcp"
    for m in ("payments-api", *ANSWERS):
        r = a.handle(m)
    r = a.handle("yes")
    assert r.data["ticket"]["payload"]["variables"]["project_id"] == "syy-payments-api"


def test_both_asks_which_one_when_not_named(tmp_path):
    a = agent(tmp_path, "aws,gcp")
    r = a.handle("I need a new cloud account")
    assert r.data["stage"] == "choosing" and "1. AWS account" in r.text and "2. GCP project" in r.text
    assert "Sorry" in a.handle("hmm").text
    r = a.handle("2")
    assert r.data["cloud"] == "gcp" and a.intake.form is a.forms["gcp"]


def test_both_choice_by_name_and_cancel(tmp_path):
    a = agent(tmp_path, "aws,gcp")
    a.handle("I want a new cloud account")
    assert a.handle("AWS please").data["cloud"] == "aws"
    a.handle("cancel")
    a.handle("request a cloud project")
    assert a.handle("cancel").text == "OK, no request started." and not a.choosing


def test_question_while_choosing_is_answered(tmp_path):
    a = agent(tmp_path, "aws,gcp")
    a.handle("I need a new cloud account")
    assert a.handle("what is the difference?").kind == "answer" and not a.choosing


def test_both_in_one_message_runs_one_after_the_other(tmp_path):
    a = agent(tmp_path, "aws,gcp")
    r = a.handle("I need an AWS account and a GCP project")
    assert r.data["cloud"] == "aws" and "one at a time" in r.text
    for m in ("rme-orders", *ANSWERS):
        a.handle(m)
    r = a.handle("yes")
    assert r.data["ticket"]["number"] == "RITM0010001"
    assert "Shall I start that request now?" in r.text and "GCP project" in r.text
    r = a.handle("yes")
    assert r.data["cloud"] == "gcp"
    for m in ("rme-orders", *ANSWERS):
        a.handle(m)
    assert a.handle("yes").data["ticket"]["number"] == "RITM0010002"


def test_declining_the_second_request(tmp_path):
    a = agent(tmp_path, "aws,gcp")
    a.handle("I need an AWS account and a GCP project")
    for m in ("rme-orders", *ANSWERS, "yes"):
        a.handle(m)
    assert a.handle("no thanks, what is a support group?").kind == "answer" and a.intake is None


def test_aws_only_both_requested_runs_aws_and_says_gcp_is_off(tmp_path):
    a = agent(tmp_path, "aws")
    r = a.handle("I need an AWS account and a GCP project")
    assert r.data["cloud"] == "aws" and "GCP project requests aren't available" in r.text
    assert a.queued == []
