"""Load a request form (fields, questions, rules) from a YAML file in forms/."""
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class Field:
    name: str
    label: str
    type: str = "text"                  # text | email
    question: str = ""
    hint: str = ""
    required: bool = True
    prefill: str = ""                   # "requester" = filled from the logged-in user
    normalize: str = ""                 # "slug" = lowercase, spaces -> hyphens
    min_length: int = 0
    max_length: int = 0
    pattern: str = ""
    not_allowed: list = field(default_factory=list)
    person_only: bool = False
    servicenow: str = ""                # variable name in the real ServiceNow form
    servicenow_ref: str = ""            # "sys_user" = the variable is a user reference: send the
                                        # sys_id of the user with this email, not the email text
    cues: list = field(default_factory=list)   # words that show a message is about THIS field


@dataclass
class Form:
    name: str
    title: str
    fields: list
    ticket: dict

    def field(self, name):
        return next(f for f in self.fields if f.name == name)


def load_form(path):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    known = set(Field.__dataclass_fields__)
    fields = []
    for raw in data["fields"]:
        unknown = set(raw) - known
        if unknown:
            raise ValueError(f"{path}: field {raw.get('name')!r} has unknown keys {sorted(unknown)}")
        fields.append(Field(**raw))
    return Form(name=data["name"], title=data["title"], fields=fields, ticket=data.get("ticket", {}))
