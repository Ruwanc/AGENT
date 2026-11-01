"""Create the ServiceNow request. Three modes (config.SERVICENOW_MODE):

    fake     save the ticket as JSON in data/servicenow/ and return a dummy number (RITM0010001...)
    dry_run  return the payload that WOULD be sent; nothing is created
    live     the real REST API (LiveServiceNow below; settings in config.py, secrets in .env)

All modes take the same input and return the same shape:
    {"number": "RITM0010001" | None, "mode": "...", "payload": {...}, "path": "..." }
"""
import json
from datetime import datetime, timezone
from pathlib import Path

import config
from config import SERVICENOW_FAKE_DIR, SERVICENOW_MODE


def build_payload(form, values):
    """Turn the collected values into a ticket payload (same shape for every mode)."""
    variables = {(f.servicenow or f.name): values.get(f.name, "") for f in form.fields
                 if f.name != "requested_for"}
    return {
        "catalog_item": form.title,
        "short_description": form.ticket.get("short_description", form.title).format(**values),
        "assignment_group": form.ticket.get("assignment_group", ""),
        "category": form.ticket.get("category", ""),
        "requested_for": values.get("requested_for", ""),
        "opened_by": "account-request-agent",
        "variables": variables,
    }


class FakeServiceNow:
    """Stand-in for ServiceNow: each request becomes a JSON file with an RITM-style number."""

    def __init__(self, folder=SERVICENOW_FAKE_DIR):
        self.folder = Path(folder)

    def _next_number(self):
        existing = [int(p.stem[4:]) for p in self.folder.glob("RITM*.json") if p.stem[4:].isdigit()]
        return f"RITM{max(existing, default=10000) + 1:07d}"

    def create_request(self, form, values):
        self.folder.mkdir(parents=True, exist_ok=True)
        payload = build_payload(form, values)
        number = self._next_number()
        record = {"number": number, "state": "Open",
                  "created": datetime.now(timezone.utc).isoformat(timespec="seconds"), **payload}
        path = self.folder / f"{number}.json"
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return {"number": number, "mode": "fake", "payload": payload, "path": str(path)}


class DryRunServiceNow:
    def create_request(self, form, values):
        return {"number": None, "mode": "dry_run", "payload": build_payload(form, values), "path": ""}


class LiveServiceNow:
    """The real ServiceNow REST API, logged in as the service account.

    catalog mode (SN_API=catalog, recommended)
        1. look up requested_for in sys_user by email -> sys_id
        2. POST /api/sn_sc/servicecatalog/items/{item}/order_now  with the variables
           -> ServiceNow creates REQ + RITM and runs the item's approvals and workflow
        3. GET the RITM number for that REQ (what the user will see in the portal)
    table mode (SN_API=table, simple first test)
        POST /api/now/table/{SN_TABLE} with short_description, description, assignment group

    `http` is a requests.Session (tests pass a fake one). Every failure becomes a
    RuntimeError with a plain message; the intake shows it and keeps the user's answers.
    """

    def __init__(self, instance=None, auth=None, username=None, password=None,
                 client_id=None, client_secret=None, api=None, catalog_item=None,
                 table=None, timeout=None, http=None):
        self.instance = (instance or config.SN_INSTANCE).rstrip("/")
        self.auth = auth or config.SN_AUTH
        self.username = username or config.SN_USERNAME
        self.password = password or config.SN_PASSWORD
        self.client_id = client_id or config.SN_CLIENT_ID
        self.client_secret = client_secret or config.SN_CLIENT_SECRET
        self.api = api or config.SN_API
        self.catalog_item = catalog_item or config.SN_CATALOG_ITEM_SYS_ID
        self.table = table or config.SN_TABLE
        self.timeout = timeout or config.SN_TIMEOUT
        self._http = http
        self._token = None

    # ------------------------------------------------------------ setup and HTTP
    def check_settings(self):
        """Return a list of missing settings (empty = OK). Secrets are never printed."""
        missing = []
        if not self.instance.startswith("https://"):
            missing.append("SN_INSTANCE (must start with https://)")
        if not self.username or not self.password:
            missing.append("SN_USERNAME / SN_PASSWORD")
        if self.auth == "oauth" and not (self.client_id and self.client_secret):
            missing.append("SN_CLIENT_ID / SN_CLIENT_SECRET (SN_AUTH=oauth)")
        if self.auth not in ("basic", "oauth"):
            missing.append("SN_AUTH must be basic or oauth")
        if self.api == "catalog" and not self.catalog_item:
            missing.append("SN_CATALOG_ITEM_SYS_ID (SN_API=catalog)")
        if self.api not in ("catalog", "table"):
            missing.append("SN_API must be catalog or table")
        return missing

    @property
    def http(self):
        if self._http is None:
            import requests
            self._http = requests.Session()
            self._http.headers.update({"Accept": "application/json", "Content-Type": "application/json"})
        return self._http

    def _auth_kwargs(self):
        if self.auth == "basic":
            return {"auth": (self.username, self.password)}
        if self._token is None:
            data = {"grant_type": "password", "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "username": self.username, "password": self.password}
            r = self._send("POST", "/oauth_token.do", data=data, auth_kwargs={})
            self._token = r.get("access_token") or ""
            if not self._token:
                raise RuntimeError("ServiceNow OAuth login did not return an access token.")
        return {"headers": {"Authorization": f"Bearer {self._token}"}}

    def _send(self, method, path, auth_kwargs=None, **kwargs):
        """One HTTP call -> parsed JSON. Turns every failure into a readable RuntimeError."""
        import requests
        if auth_kwargs is None:
            auth_kwargs = self._auth_kwargs()
        try:
            r = self.http.request(method, self.instance + path, timeout=self.timeout,
                                  **auth_kwargs, **kwargs)
        except requests.exceptions.Timeout:
            raise RuntimeError(f"ServiceNow did not answer within {self.timeout:.0f}s. "
                               "Check in ServiceNow before retrying, the request may have been created.")
        except requests.exceptions.ConnectionError:
            raise RuntimeError(f"Can't reach {self.instance}. Check SN_INSTANCE, your network and VPN.")
        if r.status_code == 401:
            raise RuntimeError("ServiceNow login failed (401). Check SN_USERNAME / SN_PASSWORD "
                               "(and the OAuth client id/secret if SN_AUTH=oauth).")
        if r.status_code == 403:
            raise RuntimeError(f"The service account is not allowed to do this (403 on {path}). "
                               "Ask the ServiceNow admins for the roles listed in the README.")
        if r.status_code == 404:
            raise RuntimeError(f"Not found (404 on {path}). Check SN_CATALOG_ITEM_SYS_ID / SN_TABLE.")
        if r.status_code >= 400:
            raise RuntimeError(f"ServiceNow error {r.status_code} on {path}: {_error_text(r)}")
        try:
            return r.json()
        except ValueError:
            raise RuntimeError(f"ServiceNow returned something that is not JSON from {path} "
                               "(often an SSO/login page: the service account needs API access).")

    # ------------------------------------------------------------ lookups
    def find_user(self, email):
        """sys_id of the active user with this email. Raises if none or several."""
        data = self._send("GET", "/api/now/table/sys_user", params={
            "sysparm_query": f"email={email}^active=true",
            "sysparm_fields": "sys_id,name,email", "sysparm_limit": "2"})
        rows = data.get("result", [])
        if not rows:
            raise RuntimeError(f"No active ServiceNow user has the email {email}.")
        if len(rows) > 1:
            raise RuntimeError(f"More than one ServiceNow user has the email {email}; ask the admins to fix it.")
        return rows[0]["sys_id"]

    def whoami(self):
        """Cheap login test: the service account's own user record."""
        data = self._send("GET", "/api/now/table/sys_user", params={
            "sysparm_query": f"user_name={self.username}", "sysparm_fields": "sys_id,name,user_name",
            "sysparm_limit": "1"})
        rows = data.get("result", [])
        return rows[0] if rows else {}

    def catalog_variables(self):
        """Variables of the catalog item (name, label, type, mandatory): to fill in the YAML."""
        data = self._send("GET", f"/api/sn_sc/servicecatalog/items/{self.catalog_item}")
        item = data.get("result", {})
        return item.get("name", ""), item.get("variables", [])

    # ------------------------------------------------------------ create
    def create_request(self, form, values):
        missing = self.check_settings()
        if missing:
            raise RuntimeError("Live ServiceNow settings missing in .env: " + ", ".join(missing))
        payload = build_payload(form, values)
        if self.api == "catalog":
            return self._order_catalog_item(form, values, payload)
        return self._insert_record(payload)

    def _order_catalog_item(self, form, values, payload):
        requested_for = self.find_user(values["requested_for"])
        variables = dict(payload["variables"])
        for f in form.fields:
            if f.servicenow_ref == "sys_user" and f.name != "requested_for" and values.get(f.name):
                variables[f.servicenow or f.name] = self.find_user(values[f.name])
        body = {"sysparm_quantity": "1", "sysparm_requested_for": requested_for, "variables": variables}
        data = self._send("POST", f"/api/sn_sc/servicecatalog/items/{self.catalog_item}/order_now", json=body)
        result = data.get("result", {})
        req_number = result.get("request_number") or result.get("number")
        req_id = result.get("request_id") or result.get("sys_id")
        number, ritm_id = req_number, None
        try:                                    # the RITM is what the user tracks; REQ if not found
            items = self._send("GET", "/api/now/table/sc_req_item", params={
                "sysparm_query": f"request={req_id}", "sysparm_fields": "number,sys_id", "sysparm_limit": "1"})
            if items.get("result"):
                number, ritm_id = items["result"][0]["number"], items["result"][0]["sys_id"]
        except RuntimeError:
            pass
        return {"number": number, "request": req_number, "sys_id": ritm_id or req_id,
                "mode": "live", "payload": payload, "path": "",
                "url": f"{self.instance}/nav_to.do?uri=sc_req_item.do?sys_id={ritm_id}" if ritm_id else ""}

    def _insert_record(self, payload):
        details = "\n".join(f"{k}: {v}" for k, v in payload["variables"].items())
        body = {"short_description": payload["short_description"],
                "description": f"Requested for: {payload['requested_for']}\n{details}\n\n"
                               f"(created by {payload['opened_by']})",
                "assignment_group": payload["assignment_group"],
                "category": payload["category"]}
        data = self._send("POST", f"/api/now/table/{self.table}", json=body,
                          params={"sysparm_input_display_value": "true",   # group by name, not sys_id
                                  "sysparm_fields": "number,sys_id"})
        result = data.get("result", {})
        return {"number": result.get("number"), "sys_id": result.get("sys_id"), "mode": "live",
                "payload": payload, "path": "",
                "url": f"{self.instance}/nav_to.do?uri={self.table}.do?sys_id={result.get('sys_id')}"}


def _error_text(response):
    try:
        err = response.json().get("error", {})
        return err.get("message", "") + (f" ({err['detail']})" if err.get("detail") else "")
    except ValueError:
        return response.text[:200]


def get_client(mode=SERVICENOW_MODE):
    clients = {"fake": FakeServiceNow, "dry_run": DryRunServiceNow, "live": LiveServiceNow}
    if mode not in clients:
        raise ValueError(f"SERVICENOW_MODE must be one of {sorted(clients)}, not {mode!r}")
    return clients[mode]()
