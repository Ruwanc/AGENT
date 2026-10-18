from rag.vault import (content_hash, extract_tags, list_notes, load_note,
                       relative_note_path, strip_image_embeds)


def _write(root, rel, text):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def test_list_notes_recurses_sorts_and_ignores_obsidian(tmp_path):
    _write(tmp_path, "b.md", "B")
    _write(tmp_path, "Pets/a.md", "A")
    _write(tmp_path, ".obsidian/workspace.md", "x")
    _write(tmp_path, "Pets/photo.png", "x")
    rel = [relative_note_path(tmp_path, p) for p in list_notes(tmp_path)]
    assert rel == ["Pets/a.md", "b.md"]


def test_relative_path_uses_forward_slashes(tmp_path):
    p = _write(tmp_path, "Deep/Folder/Note.md", "x")
    assert relative_note_path(tmp_path, p) == "Deep/Folder/Note.md"


def test_strip_image_embeds_keeps_note_embeds():
    text = "A ![[cat.png]] B ![[cat.JPG|300]] C ![[Other note]] D ![pic](img/dog.jpeg) E"
    out = strip_image_embeds(text)
    assert "cat.png" not in out and "cat.JPG" not in out and "dog.jpeg" not in out
    assert "![[Other note]]" in out
    assert all(word in out for word in "ABCDE")


def test_extract_tags_from_list_string_and_inline():
    assert extract_tags({"tags": ["pets", "#cats"]}, "") == ["cats", "pets"]
    assert extract_tags({"tags": "pets, cats"}, "") == ["cats", "pets"]
    assert extract_tags({}, "Text #health and #pets/cats.\n# Heading") == ["health", "pets/cats"]


def test_content_hash_changes_with_content():
    assert content_hash("a") == content_hash("a")
    assert content_hash("a") != content_hash("b")
    assert len(content_hash("a")) == 64


def test_load_note_fields(tmp_path):
    raw = "---\ntitle: Kitty Facts\ntags: [pets]\n---\n# Diet\nMeat. ![[x.png]]\n"
    p = _write(tmp_path, "Pets/Cats.md", raw)
    note = load_note(tmp_path, p)
    assert note["path"] == "Pets/Cats.md"
    assert note["title"] == "Kitty Facts"
    assert note["tags"] == ["pets"]
    assert note["body"].startswith("# Diet") and "x.png" not in note["body"]
    assert note["hash"] == content_hash(raw)


def test_title_defaults_to_file_name(tmp_path):
    p = _write(tmp_path, "Dogs.md", "No frontmatter here.")
    assert load_note(tmp_path, p)["title"] == "Dogs"
