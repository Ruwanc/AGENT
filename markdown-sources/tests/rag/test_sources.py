from pathlib import Path

from cet_agent.rag.chunking import chunk_note
from cet_agent.rag.sources import (chunk_id, chunk_metadata, clean_body, extract_tags,
                            guess_title, list_markdown_files, load_document,
                            load_source, relative_path)

SAMPLE_DOCS = Path(__file__).resolve().parents[2] / "docs" / "samples"


def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


# --- listing ---------------------------------------------------------------
def test_lists_md_and_markdown_and_skips_ignored(tmp_path):
    _write(tmp_path, "README.md", "x")
    _write(tmp_path, "docs/a.markdown", "x")
    _write(tmp_path, "node_modules/pkg/README.md", "x")
    _write(tmp_path, ".git/x.md", "x")
    _write(tmp_path, "notes.txt", "x")
    rel = [relative_path(tmp_path, p) for p in list_markdown_files(tmp_path)]
    assert rel == ["docs/a.markdown", "README.md"]


# --- titles ----------------------------------------------------------------
def test_title_from_frontmatter_then_h1_then_filename():
    assert guess_title({"title": "FM"}, "# H1", "x.md") == "FM"
    assert guess_title({}, "intro\n# Real Title ##\n## Sub", "x.md") == "Real Title"
    assert guess_title({}, "```\n# not a title\n```\ntext", "my-file.md") == "my-file"


def test_setext_h1_becomes_title(tmp_path):
    p = _write(tmp_path, "README.md", "My Project\n==========\n\nSome text here.\n")
    assert load_document(tmp_path, p)["title"] == "My Project"


# --- cleaning --------------------------------------------------------------
def test_images_links_and_comments_are_cleaned():
    body = ("Hi <!-- secret --> there.\n![logo](img/logo.png)\n<img src=\"a.jpg\" alt=\"x\">\n"
            "Read [the guide](guides/install.md \"Guide\") now. Bill: [pdf](files/bill.pdf)\n\n"
            "[ref]: https://example.com")
    out = clean_body(body)
    assert "secret" not in out and "logo.png" not in out and "a.jpg" not in out
    assert "Read the guide now. Bill: pdf" in out
    assert "https://example.com" not in out


def test_setext_headings_become_atx():
    body = "Title\n=====\n\nIntro.\n\nSub\n---\n\nText.\n\n- item\n---\n\nPara\n\n---\n\nEnd"
    out = clean_body(body)
    assert out.startswith("# Title")
    assert "## Sub" in out
    assert "## - item" not in out            # list item above --- is not a heading
    assert "## Para" not in out              # blank line before --- means horizontal rule


def test_code_fences_are_never_cleaned():
    body = "```md\n![x](a.png) <!-- keep --> [link](u)\nTitle\n=====\n```"
    assert clean_body(body) == body


# --- tags ------------------------------------------------------------------
def test_tags_come_only_from_frontmatter():
    meta = {"tags": "setup, install", "keywords": ["rag", "#embeddings"]}
    assert extract_tags(meta) == ["embeddings", "install", "rag", "setup"]
    assert extract_tags({}) == []


# --- full documents ----------------------------------------------------------
def test_load_doc_without_frontmatter(tmp_path):
    p = _write(tmp_path, "README.md", "# My Project\n\nIssue #42 and C# are text.\n")
    doc = load_document(tmp_path, p, source="docs")
    assert doc["title"] == "My Project"
    assert doc["source"] == "docs" and doc["path"] == "README.md"
    assert doc["tags"] == [] and doc["metadata"] == {}
    assert "Issue #42 and C# are text." in doc["body"]


def test_metadata_is_chroma_safe(tmp_path):
    raw = "---\nupdated: 2026-10-01\nauthors: [a, b]\ndraft: false\nversion: 1.2\nempty:\n---\nBody"
    doc = load_document(tmp_path, _write(tmp_path, "x.md", raw))
    assert doc["metadata"] == {"updated": "2026-10-01", "authors": "a,b",
                               "draft": False, "version": 1.2, "empty": ""}


def test_broken_frontmatter_does_not_crash(tmp_path):
    p = _write(tmp_path, "bad.md", "---\ntitle: [unclosed\n---\nStill readable text.")
    assert "Still readable text." in load_document(tmp_path, p)["body"]


def test_same_file_name_in_two_sources_gets_different_ids(tmp_path):
    a = _write(tmp_path / "A", "README.md", "# A\n\nAlpha text that is long enough to keep.")
    b = _write(tmp_path / "B", "README.md", "# B\n\nBravo text that is long enough to keep.")
    da = load_document(tmp_path / "A", a, source="a")
    db = load_document(tmp_path / "B", b, source="b")
    assert chunk_id(chunk_note(da)[0], "a") == "a:README.md::0"
    assert chunk_id(chunk_note(db)[0], "b") == "b:README.md::0"


def test_chunk_metadata_is_flat(tmp_path):
    p = _write(tmp_path, "x.md", "---\ntags: [t1, t2]\n---\n# X\n\nEnough text to make one chunk here.")
    doc = load_document(tmp_path, p, source="s")
    meta = chunk_metadata(doc, chunk_note(doc)[0])
    assert meta["tags"] == "t1,t2" and meta["source"] == "s"
    assert all(isinstance(v, (str, int, float, bool)) for v in meta.values())


# --- the sample docs ------------------------------------------------------------
def test_load_source_sample_docs():
    docs = {d["path"]: d for d in load_source({"name": "docs", "path": str(SAMPLE_DOCS)})}
    # >= : your own files (tags.md, labels.md, ...) may sit next to the samples
    assert set(docs) >= {"README.md", "chunking-test.md", "guides/install.md"}
    assert docs["README.md"]["title"] == "Petcare API"
    assert docs["guides/install.md"]["tags"] == ["install", "setup"]
    assert "architecture.png" not in docs["guides/install.md"]["body"]


def test_chunking_test_doc_end_to_end():
    doc = load_document(SAMPLE_DOCS, SAMPLE_DOCS / "chunking-test.md", "docs")
    assert doc["tags"] == ["chunking", "embeddings", "markdown", "rag", "testing"]
    chunks = chunk_note(doc)
    paths = [c["heading_path"] for c in chunks]
    assert all(len(c["text"]) <= 800 for c in chunks)
    assert "Pet Care Handbook > Closing Hashes Heading" in paths
    assert "Pet Care Handbook > Setext Heading Level Two" in paths
    assert "Second Top-Level Heading > Diet" in paths
    table_chunks = [c for c in chunks if "Food Reference" in c["heading_path"]]
    assert len(table_chunks) > 1
    assert all("| Food | Type |" in c["text"] for c in table_chunks)   # header repeated
    text = "\n".join(c["text"] for c in chunks)
    assert "cat-sleeping.png" not in text and "internal note" not in text
    assert "# This comment starts with" in text                     # code kept intact


# --- chunking fixes ------------------------------------------------------------
def test_chunks_never_exceed_limit_including_header():
    body = "## A Fairly Long Heading Name For Testing\n\n" + " ".join(["word"] * 600)
    note = {"path": "x.md", "title": "Some Title", "tags": [], "body": body}
    chunks = chunk_note(note, max_chars=300)
    assert len(chunks) > 1
    assert all(len(c["text"]) <= 300 for c in chunks)


def test_hard_cut_does_not_split_words():
    body = " ".join(f"token{i}" for i in range(300))       # no sentence punctuation
    note = {"path": "x.md", "title": "T", "tags": [], "body": body}
    words = set(body.split())
    for c in chunk_note(note, max_chars=200):
        assert set(c["text"].split("\n\n", 1)[1].split()) <= words
