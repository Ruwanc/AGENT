"""Vector DB tests. A fake embedder (word hashing) replaces Ollama, so these run offline."""
import hashlib
import math
import re
import shutil
from pathlib import Path

import pytest

from cet_agent.rag.chunking import chunk_note
from cet_agent.rag.indexer import sync
from cet_agent.rag.retriever import expand_sections, search
from cet_agent.rag.sources import load_source
from cet_agent.rag.store import get_collection, reset_collection

SAMPLE = Path(__file__).resolve().parents[2] / "docs" / "samples"
DIM = 128


def fake_vec(text):
    v = [0.0] * DIM
    for w in re.findall(r"[a-z]+", text.lower()):
        v[int(hashlib.md5(w.encode()).hexdigest(), 16) % DIM] += 1
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def fake_embed(texts):
    return [fake_vec(t) for t in texts]


@pytest.fixture
def env(tmp_path):
    docs = tmp_path / "docs"
    shutil.copytree(SAMPLE, docs)        # docs/samples: the 3 sample files only
    col = get_collection(path=tmp_path / "db", name="test_chunks", embedding_model="fake")
    sources = [{"name": "docs", "path": str(docs)}]
    run = lambda **kw: sync(sources=sources, collection=col, embed_fn=fake_embed, log=lambda *_: None, **kw)
    return docs, col, run, sources


def expected_chunk_count(sources):
    return sum(len(chunk_note(d)) for s in sources for d in load_source(s))


def test_first_run_adds_every_chunk(env):
    docs, col, run, sources = env
    stats = run()
    assert stats["added"] == 3 and stats["updated"] == 0
    assert col.count() == expected_chunk_count(sources) == stats["total_chunks"]


def test_records_have_text_metadata_and_ids(env):
    _, col, run, _ = env
    run()
    rec = col.get(ids=["docs:guides/install.md::1"], include=["documents", "metadatas", "embeddings"])
    assert rec["documents"][0].startswith("Installation Guide > Install the Petcare API > Steps")
    m = rec["metadatas"][0]
    assert m["source"] == "docs" and m["note_path"] == "guides/install.md" and m["tags"] == "install,setup"
    assert len(rec["embeddings"][0]) == DIM


def test_second_run_skips_unchanged_files(env):
    _, col, run, _ = env
    run()
    calls = []
    stats = sync(sources=env[3], collection=col, log=lambda *_: None,
                 embed_fn=lambda t: calls.append(t) or fake_embed(t))
    assert stats["unchanged"] == 3 and stats["chunks_written"] == 0 and calls == []


def test_changed_file_is_replaced_not_duplicated(env):
    docs, col, run, sources = env
    run()
    f = docs / "guides" / "install.md"
    f.write_text(f.read_text() + "\n## Uninstall\n\nRun pip uninstall petcare-api to remove the package.\n")
    stats = run()
    assert stats["updated"] == 1 and stats["unchanged"] == 2
    assert col.count() == expected_chunk_count(sources)
    paths = [m["heading_path"] for m in col.get(where={"note_path": "guides/install.md"})["metadatas"]]
    assert "Install the Petcare API > Uninstall" in paths


def test_deleted_file_is_removed(env):
    docs, col, run, _ = env
    run()
    (docs / "README.md").unlink()
    stats = run()
    assert stats["deleted"] == 1
    assert col.get(where={"note_path": "README.md"})["ids"] == []


def test_missing_folder_keeps_chunks(env, tmp_path):
    docs, col, run, _ = env
    run()
    before = col.count()
    stats = sync(sources=[{"name": "docs", "path": str(tmp_path / "gone")}], collection=col,
                 embed_fn=fake_embed, log=lambda *_: None)
    assert stats["deleted"] == 0 and col.count() == before


def test_search_returns_relevant_chunk(env):
    _, col, run, _ = env
    run()
    hits = search("activate the virtual environment on Windows", k=3, collection=col,
                  embed_fn=fake_vec)
    assert hits and hits[0]["note_path"] == "guides/install.md"
    assert 0 <= hits[0]["similarity"] <= 1
    assert all(h["source"] == "docs" for h in search("port", source="docs", collection=col, embed_fn=fake_vec))


def test_wrong_embedding_model_is_refused(tmp_path):
    get_collection(path=tmp_path, name="m_chunks", embedding_model="model-a")
    with pytest.raises(RuntimeError, match="--reset"):
        get_collection(path=tmp_path, name="m_chunks", embedding_model="model-b")
    reset_collection(path=tmp_path, name="m_chunks")
    assert get_collection(path=tmp_path, name="m_chunks", embedding_model="model-b").count() == 0


def test_expand_sections_adds_the_rest_of_a_split_table(env):
    _, col, run, _ = env
    run()
    table = [m for m in col.get(include=["metadatas"])["metadatas"] if "Food Reference" in m["heading_path"]]
    assert len(table) == 3                                    # the big table is stored as 3 chunks
    piece2 = next(m for m in table if m["chunk_index"] == min(t["chunk_index"] for t in table) + 1)
    rec = col.get(ids=[f"docs:{piece2['note_path']}::{piece2['chunk_index']}"], include=["documents"])
    hit = {"id": rec["ids"][0], "text": rec["documents"][0], "similarity": 0.7, "distance": 0.3, **piece2}
    out = expand_sections([hit], collection=col)
    assert [o["chunk_index"] for o in out] == sorted(t["chunk_index"] for t in table)   # all 3, in order
    assert sum(o.get("expanded", False) for o in out) == 2
    assert expand_sections([hit], collection=col, max_chars=len(hit["text"])) == [hit]  # budget respected
