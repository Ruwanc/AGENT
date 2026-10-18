"""Read the Obsidian vault: find notes, parse frontmatter, clean the body.

Pure file reading. No Ollama, no Chroma. Output feeds chunking.chunk_note().

YOUR TASK (Phase 1): replace each `raise NotImplementedError` and make
`pytest tests/test_vault.py` pass. Hints are in each docstring.
"""
import hashlib
import re
from pathlib import Path

import frontmatter   # pip install python-frontmatter

from config import IGNORED_DIRS, IMAGE_EXTENSIONS

# ![[photo.png]]  or  ![[photo.png|300]]   (Obsidian wiki embed)
WIKI_EMBED_RE = re.compile(r"!\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
# ![alt text](images/photo.png)            (standard Markdown image)
MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)[^)]*\)")
# inline #tag  (not "# Heading", not "abc#def", not inside a URL fragment)
INLINE_TAG_RE = re.compile(r"(?<![\w#/])#([A-Za-z][\w/-]*)")


def list_notes(vault_path):
    """Return a sorted list of Path objects for every .md file in the vault.

    - Recurse into sub-folders (hint: Path.rglob("*.md")).
    - Skip any file whose path contains a folder in IGNORED_DIRS
      (hint: set(p.relative_to(vault).parts) & IGNORED_DIRS).
    - Sort so the order is the same on every run and every OS.
    """
    raise NotImplementedError


def relative_note_path(vault_path, file_path):
    """'C:\\Vault\\Pets\\Cats.md' -> 'Pets/Cats.md'.

    Vault-relative and ALWAYS forward slashes, so the same note gets the same
    Chroma ID on Windows, macOS and Linux (hint: .relative_to(...).as_posix()).
    """
    raise NotImplementedError


def strip_image_embeds(text):
    """Remove image embeds, keep everything else.

    - Remove ![[x.png]] / ![[x.png|300]] only when the target ends in an
      IMAGE_EXTENSIONS suffix. Keep ![[Other note]] (that is a note embed).
    - Remove ![alt](x.png) when the target is an image.
    Hint: re.sub with a function as the replacement lets you decide per match.
    """
    raise NotImplementedError


def extract_tags(metadata, body):
    """Merge frontmatter tags and inline #tags into a sorted, de-duplicated list.

    Frontmatter `tags` may be a list (["a", "b"]), a string ("a, b" or "a b"),
    or missing. Strip any leading '#'. Inline tags come from INLINE_TAG_RE.
    Ignore #lines inside code fences if you want extra credit (not tested).
    """
    raise NotImplementedError


def content_hash(raw_text):
    """SHA-256 hex digest of the raw file text (frontmatter included, so a tag
    change also triggers re-indexing in Phase 6)."""
    raise NotImplementedError


def load_note(vault_path, file_path):
    """Read one note and return the dict chunk_note() expects, plus a hash:

        {"path": "Pets/Cats.md", "title": "Cats", "tags": ["pets"],
         "body": "<markdown without frontmatter or image embeds>",
         "hash": "<sha256 of the raw file>"}

    - Read with encoding="utf-8".
    - frontmatter.loads(raw) gives .metadata (dict) and .content (body).
    - title = metadata["title"] if present, else the file name without .md.
    """
    raise NotImplementedError


def load_vault(vault_path):
    """Yield load_note(...) for every note from list_notes(...)."""
    for file_path in list_notes(vault_path):
        yield load_note(vault_path, file_path)


if __name__ == "__main__":
    from config import VAULT_PATH

    notes = list(load_vault(VAULT_PATH))
    print(f"{len(notes)} notes in {VAULT_PATH}")
    for n in notes[:10]:
        print(f"  {n['path']:<40} tags={n['tags']} chars={len(n['body'])} hash={n['hash'][:8]}")
