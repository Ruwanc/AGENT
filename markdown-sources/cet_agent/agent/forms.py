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
class Derived:
    """A value the agent works out itself from other answers (never asked), e.g. the GCP
    project ID "syy-{project_name}". Shown in the summary and sent to ServiceNow."""
    name: str
    label: str
    template: str                       # Python format string using field names
    servicenow: str = ""                # variable name in the real ServiceNow form


@dataclass
class Form:
    name: str
    title: str
    fields: list
    ticket: dict
    derived: list = field(default_factory=list)

    def field(self, name):
        return next(f for f in self.fields if f.name == name)

    def derive(self, values):
        """Derived values that can be worked out from the answers given so far."""
        out = {}
        for d in self.derived:
            try:
                out[d.name] = d.template.format(**values)
            except KeyError:            # a field it needs isn't answered yet
                pass
        return out


def _build(cls, raw, path):
    unknown = set(raw) - set(cls.__dataclass_fields__)
    if unknown:
        raise ValueError(f"{path}: {cls.__name__.lower()} {raw.get('name')!r} has unknown keys {sorted(unknown)}")
    return cls(**raw)


def load_form(path):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    fields = [_build(Field, raw, path) for raw in data["fields"]]
    derived = [_build(Derived, raw, path) for raw in data.get("derived", [])]
    return Form(name=data["name"], title=data["title"], fields=fields,
                ticket=data.get("ticket", {}), derived=derived)
