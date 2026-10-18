# markdown-sources

Load and chunk plain Markdown files (READMEs, docs sites, wiki/Confluence/Notion
exports) from one or more folders, ready for embedding.

```
markdown-sources/
  config.py                   SOURCES (folders) + chunk settings
  md_rag/sources.py           list files, frontmatter, cleaning, tags, titles, IDs, metadata
  md_rag/chunking.py          heading-aware chunker (tables, code fences, size limit)
  md_rag/langchain_loader.py  optional: same output as LangChain Documents
  scripts/inspect_chunks.py   report of every chunk, no Ollama/Chroma needed
  tests/                      28 tests (pytest)
  sample_docs/                test files (README, guide, full chunking-test.md)
```

## Run (macOS / Linux)

```bash
cd ~/MyLearning/AGENT
source .venv/bin/activate
pip install -r markdown-sources/requirements.txt
cd markdown-sources
pytest -q
python -m md_rag.sources                 # one line per loaded file
python -m scripts.inspect_chunks         # every chunk
python -m scripts.inspect_chunks docs --full
python -m md_rag.langchain_loader        # LangChain Documents
```

## Add your own folders

Edit `SOURCES` in `config.py` (or set `DOCS_PATH` for the default one):

```python
SOURCES = [
    {"name": "docs", "path": "/Users/you/repos/platform/docs"},
    {"name": "runbooks", "path": "/Users/you/runbooks"},
]
```

## What the loader does

| Item | Behaviour |
|---|---|
| Frontmatter | optional; becomes Chroma-safe metadata (dates → ISO text, lists → "a,b") |
| Tags | from frontmatter `tags`, `tag`, `keywords` or `categories` |
| Title | frontmatter `title` → first `# H1` (or setext `Title / ===`) → file name |
| Headings | ATX (`## A`, `## A ##`) and setext (`A` / `---`) |
| Removed | images `![](x.png)`, `<img>`, `<!-- comments -->`, link reference definitions |
| Links | `[text](url)` → `text` |
| Code fences | never changed |
| Chunk IDs | `"{source}:{path}::{chunk_index}"` — unique across folders |
