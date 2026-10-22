"""Create the ServiceNow request. Three modes (config.SERVICENOW_MODE):

    fake     save the ticket as JSON in data/servicenow/ and return a dummy number (RITM0010001...)
    dry_run  return the payload that WOULD be sent; nothing is created
    live     the real REST API, not built yet: needs the instance URL, the catalog item
             (or table) and its variable names, and credentials (see README)

All modes take the same input and return the same shape:
    {"number": "RITM0010001" | None, "mode": "...", "payload": {...}, "path": "..." }
"""
import json
from datetime import datetime, timezone
from pathlib import Path

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
    def create_request(self, form, values):
        raise RuntimeError(
            "Live ServiceNow is not set up yet. It needs the instance URL, the catalog item "
            "(sys_id and variable names) and credentials. Use SERVICENOW_MODE=fake or dry_run for now."
        )


def get_client(mode=SERVICENOW_MODE):
    clients = {"fake": FakeServiceNow, "dry_run": DryRunServiceNow, "live": LiveServiceNow}
    if mode not in clients:
        raise ValueError(f"SERVICENOW_MODE must be one of {sorted(clients)}, not {mode!r}")
    return clients[mode]()
