"""Test the live ServiceNow connection step by step, WITHOUT creating anything.

Run from the project root after filling in .env:
    python -m scripts.check_servicenow
    python -m scripts.check_servicenow --email jane.doe@company.com   # also test a user lookup

Checks: settings present -> login works -> user lookup -> catalog item + its variables
(so you can copy the real variable names into forms/aws_account.yaml) -> dry-run payload.
"""
import argparse
import json
import sys

import config
from md_rag.forms import load_form
from md_rag.servicenow import LiveServiceNow, build_payload

parser = argparse.ArgumentParser(description="Check the live ServiceNow setup (read-only)")
parser.add_argument("--email", help="a user email to look up in sys_user")
args = parser.parse_args()

sn = LiveServiceNow()
failed = False


def step(name, fn):
    global failed
    try:
        detail = fn()
        print(f"PASS  {name}" + (f": {detail}" if detail else ""))
        return True
    except RuntimeError as e:
        failed = True
        print(f"FAIL  {name}: {e}")
        return False


print(f"instance: {sn.instance or '(not set)'}   auth: {sn.auth}   api: {sn.api}   user: {sn.username or '(not set)'}\n")

missing = sn.check_settings()
if missing:
    print("FAIL  settings: missing " + ", ".join(missing))
    sys.exit("\nFill these in .env (copy .env.example), then run again.")
print("PASS  settings")

if not step("login", lambda: (lambda me: f"logged in as {me.get('name') or sn.username}")(sn.whoami())):
    sys.exit(1)

if args.email:
    step(f"user lookup {args.email}", lambda: f"sys_id {sn.find_user(args.email)}")

form = load_form(config.ACCOUNT_FORM)
if sn.api == "catalog":
    def show_item():
        name, variables = sn.catalog_variables()
        print(f"PASS  catalog item: {name}")
        print("      variables in ServiceNow (name / label / type / mandatory):")
        for v in variables:
            print(f"        {v.get('name', ''):<28} {v.get('label', ''):<34} {v.get('type', '')!s:<5} "
                  f"{'yes' if v.get('mandatory') else ''}")
        real = {v.get("name") for v in variables}
        ours = {f.servicenow or f.name for f in form.fields if f.name != "requested_for"}
        unknown = sorted(ours - real)
        if unknown:
            print(f"WARN  these servicenow: names in the YAML are not in the item: {unknown}")
        mandatory = sorted(v.get("name") for v in variables if v.get("mandatory") and v.get("name") not in ours)
        if mandatory:
            print(f"WARN  mandatory item variables the form does not collect: {mandatory}")
    try:
        show_item()
    except RuntimeError as e:
        failed = True
        print(f"FAIL  catalog item: {e}")
else:
    print(f"INFO  table mode: records go to the {sn.table} table")

sample = {f.name: f"<{f.name}>" for f in form.fields}
print("\nThis is the payload shape the agent builds (values are placeholders):")
print(json.dumps(build_payload(form, sample), indent=2))
print("\nAll checks passed. Next: SERVICENOW_MODE=live python -m scripts.agent" if not failed
      else "\nFix the FAIL lines above first.")
sys.exit(1 if failed else 0)
