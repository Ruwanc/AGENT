"""LiveServiceNow against a fake HTTP session: no network, no real instance."""
import pytest
import requests

import config
from md_rag.forms import load_form
from md_rag.servicenow import LiveServiceNow

FORM = load_form(config.ACCOUNT_FORM)
VALUES = {"requested_for": "jane.doe@corp.com", "account_name": "rme-orders-nonprod",
          "app_team_name": "RME", "support_group": "RME Support",
          "technical_owner": "tom.lee@corp.com", "budget_approver": "ann.wu@corp.com"}
USERS = {"jane.doe@corp.com": "U_JANE", "tom.lee@corp.com": "U_TOM", "ann.wu@corp.com": "U_ANN"}


class Resp:
    def __init__(self, status, data):
        self.status_code, self._data, self.text = status, data, str(data)

    def json(self):
        if self._data is None:
            raise ValueError("not json")
        return self._data


class FakeHTTP:
    """Records calls and answers like a tiny ServiceNow."""

    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def request(self, method, url, timeout=None, **kw):
        self.calls.append((method, url, kw))
        if self.fail == "timeout":
            raise requests.exceptions.Timeout()
        if self.fail:
            return Resp(self.fail, {"error": {"message": "nope"}})
        if url.endswith("/oauth_token.do"):
            return Resp(200, {"access_token": "TOKEN"})
        if "/api/now/table/sys_user" in url:
            email = kw["params"]["sysparm_query"].split("^")[0].removeprefix("email=")
            return Resp(200, {"result": [{"sys_id": USERS[email]}] if email in USERS else []})
        if url.endswith("/order_now"):
            return Resp(200, {"result": {"request_number": "REQ0012345", "request_id": "R1"}})
        if "/api/now/table/sc_req_item" in url:
            return Resp(200, {"result": [{"number": "RITM0054321", "sys_id": "RI1"}]})
        if "/api/now/table/incident" in url:
            return Resp(201, {"result": {"number": "INC0001", "sys_id": "I1"}})
        return Resp(404, {})


def client(http, **kw):
    base = dict(instance="https://dev1.service-now.com", auth="basic", username="svc", password="pw",
                api="catalog", catalog_item="CAT1", http=http)
    return LiveServiceNow(**{**base, **kw})


def test_catalog_order_returns_ritm_and_sends_requested_for_sys_id():
    http = FakeHTTP()
    t = client(http).create_request(FORM, VALUES)
    assert t["number"] == "RITM0054321" and t["request"] == "REQ0012345" and t["mode"] == "live"
    assert "sc_req_item.do?sys_id=RI1" in t["url"]
    order = next(c for c in http.calls if c[1].endswith("/order_now"))
    assert order[1] == "https://dev1.service-now.com/api/sn_sc/servicecatalog/items/CAT1/order_now"
    assert order[2]["json"]["sysparm_requested_for"] == "U_JANE"
    assert order[2]["json"]["variables"]["account_name"] == "rme-orders-nonprod"
    assert order[2]["auth"] == ("svc", "pw")


def test_user_reference_fields_are_sent_as_sys_ids():
    form = load_form(config.ACCOUNT_FORM)
    form.field("budget_approver").servicenow_ref = "sys_user"
    http = FakeHTTP()
    client(http).create_request(form, VALUES)
    variables = next(c for c in http.calls if c[1].endswith("/order_now"))[2]["json"]["variables"]
    assert variables[form.field("budget_approver").servicenow or "budget_approver"] == "U_ANN"
    assert variables[form.field("technical_owner").servicenow or "technical_owner"] == "tom.lee@corp.com"


def test_unknown_requester_is_a_clear_error():
    with pytest.raises(RuntimeError, match="No active ServiceNow user"):
        client(FakeHTTP()).create_request(FORM, {**VALUES, "requested_for": "ghost@corp.com"})


def test_table_mode_inserts_with_display_values():
    http = FakeHTTP()
    t = client(http, api="table", table="incident").create_request(FORM, VALUES)
    assert t["number"] == "INC0001"
    method, url, kw = http.calls[-1]
    assert method == "POST" and url.endswith("/api/now/table/incident")
    assert kw["params"]["sysparm_input_display_value"] == "true"
    assert kw["json"]["assignment_group"] == "Cloud Engineering"
    assert "rme-orders-nonprod" in kw["json"]["description"]


def test_oauth_gets_a_token_once_and_uses_bearer():
    http = FakeHTTP()
    client(http, auth="oauth", client_id="cid", client_secret="sec").create_request(FORM, VALUES)
    assert sum(c[1].endswith("/oauth_token.do") for c in http.calls) == 1
    order = next(c for c in http.calls if c[1].endswith("/order_now"))
    assert order[2]["headers"]["Authorization"] == "Bearer TOKEN"


@pytest.mark.parametrize("fail, message", [(401, "login failed"), (403, "not allowed"),
                                           (404, "Not found"), (500, "error 500"),
                                           ("timeout", "did not answer")])
def test_http_failures_become_readable_errors(fail, message):
    with pytest.raises(RuntimeError, match=message):
        client(FakeHTTP(fail=fail)).create_request(FORM, VALUES)


def test_missing_settings_are_listed_without_calling_servicenow():
    http = FakeHTTP()
    sn = client(http, instance="dev1.service-now.com", catalog_item=None, password=None)
    sn.catalog_item, sn.password = "", ""
    with pytest.raises(RuntimeError, match="SN_INSTANCE.*SN_USERNAME.*SN_CATALOG_ITEM_SYS_ID"):
        sn.create_request(FORM, VALUES)
    assert http.calls == []


def test_intake_keeps_answers_when_servicenow_fails():
    from md_rag.intake import Intake
    intake = Intake(FORM, requester=VALUES["requested_for"], extract_fn=lambda *a: {},
                    servicenow=client(FakeHTTP(fail=401)))
    intake.values.update(VALUES)
    intake.stage = "confirming"
    reply = intake.handle("yes")
    assert "login failed" in reply and intake.stage == "confirming" and intake.values == VALUES
