from md_rag.chunking import chunk_note, split_by_headings, split_long_section


def test_nested_headings_give_paths():
    body = "# Cats\nIntro.\n## Diet\nMeat.\n### Treats\nTuna.\n## Health\nVaccines."
    paths = [p for p, _ in split_by_headings(body)]
    assert paths == ["Cats", "Cats > Diet", "Cats > Diet > Treats", "Cats > Health"]


def test_text_before_first_heading_uses_title():
    sections = split_by_headings("Loose text.\n# A\nBody.", title="My Note")
    assert sections[0] == ("My Note", "Loose text.")


def test_heading_inside_code_fence_is_ignored():
    body = "# Setup\n```bash\n# install deps\npip install x\n```\nDone."
    paths = [p for p, _ in split_by_headings(body)]
    assert paths == ["Setup"]


def test_hash_word_is_not_a_heading():
    sections = split_by_headings("# A\n#tag in text")
    assert len(sections) == 1 and "#tag" in sections[0][1]


def test_empty_section_is_dropped():
    paths = [p for p, _ in split_by_headings("# A\n# B\nText.")]
    assert paths == ["B"]


def test_long_section_respects_cap():
    text = "\n\n".join(f"Paragraph {i}. " + "word " * 40 for i in range(20))
    pieces = split_long_section(text, max_chars=500)
    assert len(pieces) > 1
    assert all(len(p) <= 500 for p in pieces)


def test_giant_single_paragraph_is_still_split():
    pieces = split_long_section("x" * 2500, max_chars=1000)
    assert all(len(p) <= 1000 for p in pieces)
    assert "".join(pieces) == "x" * 2500


def _make_table(n_rows):
    rows = "\n".join(f"| Food{i} | Type{i} | Weekly |" for i in range(n_rows))
    return "| Food | Type | Frequency |\n|---|---|---|\n" + rows


def test_small_table_stays_whole():
    table = _make_table(3)
    assert split_long_section("Intro.\n\n" + table, max_chars=500) == ["Intro.\n\n" + table]


def test_big_table_splits_between_rows_and_repeats_header():
    table = _make_table(20)
    pieces = split_long_section(table, max_chars=150)
    assert len(pieces) > 1
    for p in pieces:
        assert len(p) <= 150
        assert p.startswith("| Food | Type | Frequency |\n|---|---|---|")
        assert all(line.endswith("|") for line in p.splitlines())   # no half rows
    body_rows = [l for p in pieces for l in p.splitlines()[2:]]
    assert body_rows == table.splitlines()[2:]                       # every row kept, in order


def test_text_with_pipes_is_not_treated_as_table():
    text = "a | b " * 100
    assert all(len(p) <= 100 for p in split_long_section(text, max_chars=100))


def test_chunk_note_fields_and_prefix():
    note = {"path": "Pets/Cats.md", "title": "Cats", "tags": ["pets"],
            "body": "## Diet\nCats are obligate carnivores and need meat."}
    chunks = chunk_note(note, min_chars=10)
    assert len(chunks) == 1
    c = chunks[0]
    assert c["text"].startswith("Cats > Diet\n\n")
    assert c["note_path"] == "Pets/Cats.md" and c["chunk_index"] == 0


def test_tiny_chunks_are_skipped():
    note = {"path": "a.md", "title": "A", "tags": [], "body": "# H\nhi"}
    assert chunk_note(note, min_chars=30) == []
