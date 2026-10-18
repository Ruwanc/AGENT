"""Load Markdown files from one or more folders ("sources").

Pure file reading: no Ollama, no Chroma. Each loaded document is a dict that
md_rag.chunking.chunk_note() accepts, plus source info and a content hash:

    {"source": "docs", "path": "guides/install.md", "title": "Install",
     "tags": ["setup"], "body": "<cleaned markdown>", "hash": "<sha256>",
     "metadata": {...frontmatter, Chroma-safe...}}
"""
import datetime as dt
import hashlib
import re
from pathlib import Path

import frontmatter

from config import IGNORED_DIRS, IMAGE_EXTENSIONS, MARKDOWN_SUFFIXES, SOURCES, TAG_KEYS

# --- patterns -------------------------------------------------------------
FENCE_RE = re.compile(r"^\s*(```|~~~)")
H1_RE = re.compile(r"^#\s+(.+?)(?:\s+#+)?\s*$")
SETEXT_RE = re.compile(r"^(=+|-+)\s*$")                                               # ==== or ---- under a line
MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")   # ![alt](x.png "t")
MD_LINK_RE = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")          # [text](url "t")
REF_DEF_RE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s+\S+.*$", re.M)                          # [1]: https://...
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
HTML_IMG_RE = re.compile(r"<img\b[^>]*>", re.I)


# --- small helpers ----------------------------------------------------------
def _is_image(target):
    return Path(target.split("?")[0].strip()).suffix.lower() in IMAGE_EXTENSIONS


def _outside_code(text, fn):
    """Apply fn(text) only to the parts of text that are NOT inside code fences."""
    out, buffer, in_fence = [], [], False

    def flush():
        if buffer:
            out.append("\n".join(buffer) if in_fence else fn("\n".join(buffer)))
            buffer.clear()

    for line in text.split("\n"):
        if FENCE_RE.match(line):
            if not in_fence:
                flush()
                in_fence = True
                buffer.append(line)
            else:
                buffer.append(line)
                flush()
                in_fence = False
            continue
        buffer.append(line)
    flush()
    return "\n".join(out)


def _setext_to_atx(text):
    """'Title\\n=====' -> '# Title' and 'Sub\\n-----' -> '## Sub' (common in READMEs).

    Only when the line above is plain text, so '---' under a list, table,
    quote or blank line (a horizontal rule) is left alone.
    """
    lines, out = text.split("\n"), []
    for line in lines:
        prev = out[-1] if out else ""
        if (SETEXT_RE.match(line) and prev.strip()
                and not prev.lstrip().startswith(("#", "|", "-", "*", "+", ">", "```", "~~~"))
                and not re.match(r"^\s*\d+[.)]\s", prev)):
            out[-1] = ("# " if line.lstrip()[0] == "=" else "## ") + prev.strip()
        else:
            out.append(line)
    return "\n".join(out)


def _chroma_safe(value):
    """Chroma metadata values must be str, int, float or bool (no lists, dates, None)."""
    if isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    if isinstance(value, (list, tuple, set)):
        return ",".join(str(v) for v in value)
    if value is None:
        return ""
    return str(value)


# --- public functions --------------------------------------------------------
def list_markdown_files(root):
    """Sorted list of Markdown files under root, skipping IGNORED_DIRS."""
    root = Path(root)
    files = [
        p for p in root.rglob("*")
        if p.is_file()
        and p.suffix.lower() in MARKDOWN_SUFFIXES
        and not set(p.relative_to(root).parts[:-1]) & IGNORED_DIRS
    ]
    return sorted(files, key=lambda p: p.relative_to(root).as_posix().lower())


def relative_path(root, file_path):
    """Source-relative path with forward slashes: 'guides/install.md'."""
    return Path(file_path).relative_to(root).as_posix()


def content_hash(raw_text):
    return hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def clean_body(body):
    """Remove noise that hurts embeddings; keep the meaning. Code fences are untouched.

    - setext headings (Title / =====) become '# Title' so the chunker sees them
    - image embeds (![alt](x.png), <img ...>) and <!-- comments --> are removed
    - [text](url) becomes text; reference definitions ([1]: url) are removed
    - extra blank lines are collapsed
    """
    def clean(text):
        text = HTML_COMMENT_RE.sub("", text)
        text = _setext_to_atx(text)
        text = MD_IMAGE_RE.sub(lambda m: "" if _is_image(m.group(2)) else m.group(0), text)
        text = HTML_IMG_RE.sub("", text)
        text = MD_LINK_RE.sub(lambda m: m.group(1), text)
        text = REF_DEF_RE.sub("", text)
        text = re.sub(r"[ \t]+\n", "\n", text)        # trailing spaces left by removals
        return re.sub(r"\n{3,}", "\n\n", text)         # collapse extra blank lines

    return _outside_code(body, clean).strip()


def extract_tags(metadata):
    """Tags from frontmatter (any key in TAG_KEYS), as a sorted, de-duplicated list.

    Values may be a list (["a", "b"]) or a string ("a, b" or "a b").
    """
    tags = set()
    for key in TAG_KEYS:
        raw = metadata.get(key) or []
        if isinstance(raw, str):
            raw = re.split(r"[,\s]+", raw)
        tags.update(str(t).strip().lstrip("#") for t in raw if str(t).strip().lstrip("#"))
    return sorted(tags)


def guess_title(metadata, body, file_path):
    """Frontmatter title > first '# H1' line > file name."""
    if metadata.get("title"):
        return str(metadata["title"]).strip()
    in_fence = False
    for line in body.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
        elif not in_fence and (m := H1_RE.match(line)):
            return m.group(1).strip()
    return Path(file_path).stem


def load_document(root, file_path, source="default"):
    """Read one Markdown file and return the document dict (see module docstring)."""
    raw = Path(file_path).read_text(encoding="utf-8-sig")    # -sig drops a Windows BOM
    try:
        post = frontmatter.loads(raw)
        metadata, body = dict(post.metadata), post.content
    except Exception:                                         # broken YAML: keep the text
        metadata, body = {}, raw

    body = clean_body(body)
    return {
        "source": source,
        "path": relative_path(root, file_path),
        "title": guess_title(metadata, body, file_path),
        "tags": extract_tags(metadata),
        "body": body,
        "hash": content_hash(raw),
        "metadata": {k: _chroma_safe(v) for k, v in metadata.items() if k not in TAG_KEYS},
    }


def load_source(source):
    """Yield every document of one source dict from config.SOURCES."""
    root = Path(source["path"]).expanduser()
    if not root.is_dir():
        raise FileNotFoundError(f"source {source['name']!r}: folder not found: {root}")
    for file_path in list_markdown_files(root):
        yield load_document(root, file_path, source["name"])


def load_all(sources=SOURCES):
    """Yield documents from every source, skipping (and reporting) missing folders."""
    for source in sources:
        try:
            yield from load_source(source)
        except FileNotFoundError as e:
            print(f"[skip] {e}")


def chunk_id(chunk, source):
    """Unique, deterministic Chroma ID: 'docs:guides/install.md::3'."""
    return f"{source}:{chunk['note_path']}::{chunk['chunk_index']}"


def chunk_metadata(doc, chunk):
    """Flat, Chroma-safe metadata for one chunk."""
    return {
        "source": doc["source"],
        "note_path": doc["path"],
        "title": doc["title"],
        "heading_path": chunk["heading_path"],
        "chunk_index": chunk["chunk_index"],
        "tags": ",".join(doc["tags"]),
        "hash": doc["hash"],
    }


if __name__ == "__main__":
    for doc in load_all():
        print(f"[{doc['source']}] {doc['path']:<40} title={doc['title']!r} "
              f"tags={doc['tags']} chars={len(doc['body'])}")
