"""Check one answer against its field's rules. Plain Python: the LLM never decides validity.

validate(field, raw) -> (ok, value, error)
    ok     True if the value can be used
    value  the cleaned value (e.g. lowercased email, slugified name)
    error  a short message saying what is wrong (empty when ok)
"""
import re

from config import ALLOWED_EMAIL_DOMAINS

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+'-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
# name parts that usually mean a shared mailbox rather than a person (checked as whole words)
TEAM_MAILBOX_WORDS = {"team", "group", "dl", "support", "noreply", "no-reply", "admin", "ops",
                      "devops", "cloudops", "helpdesk", "service", "services", "list", "info"}


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def validate(field, raw, allowed_domains=None):
    allowed_domains = ALLOWED_EMAIL_DOMAINS if allowed_domains is None else allowed_domains
    text = " ".join(str(raw or "").split())          # trim + collapse spaces
    if not text:
        return False, "", f"{field.label} can't be empty."
    if field.type == "email":
        return _validate_email(field, text, allowed_domains)
    return _validate_text(field, text)


def _validate_text(field, text):
    value = slugify(text) if field.normalize == "slug" else text
    if field.min_length and len(value) < field.min_length:
        return False, value, f"{field.label} must be at least {field.min_length} characters."
    if field.max_length and len(value) > field.max_length:
        return False, value, f"{field.label} must be at most {field.max_length} characters (it has {len(value)})."
    if field.pattern and not re.fullmatch(field.pattern, value):
        return False, value, f"“{value}” isn't a valid {field.label}."
    if value.lower() in {w.lower() for w in field.not_allowed}:
        return False, value, f"“{value}” is too generic for {field.label}; say what the account is for."
    return True, value, ""


def _validate_email(field, text, allowed_domains):
    emails = EMAIL_RE.findall(text)
    if not emails:
        return False, text, f"“{text}” doesn't look like an email address."
    if len({e.lower() for e in emails}) > 1:
        return False, text, f"{field.label} takes only one email address (you gave {len(emails)})."
    value = emails[0].lower()
    local, domain = value.split("@", 1)
    if allowed_domains and domain not in {d.lower() for d in allowed_domains}:
        return False, value, f"{value} is not a company address (allowed: {', '.join(allowed_domains)})."
    if field.person_only and (set(re.split(r"[._+-]", local)) & TEAM_MAILBOX_WORDS
                              or local.endswith(("team", "group", "support"))):
        return False, value, f"{value} looks like a team mailbox; {field.label} must be a person's email."
    return True, value, ""
