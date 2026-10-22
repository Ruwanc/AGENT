# markdown-sources

Load, chunk, embed and store plain Markdown files (READMEs, docs sites,
wiki/Confluence/Notion exports) from one or more folders in a local ChromaDB,
using an embedding model served by Ollama. Then search them, ask questions and get answers with sources from a local chat model,
or request a new AWS account in the same chat (creates a ServiceNow ticket; fake for now).

```
markdown-sources/
  config.py                   SOURCES (folders) + chunk settings
  md_rag/sources.py           list files, frontmatter, cleaning, tags, titles, IDs, metadata
  md_rag/chunking.py          heading-aware chunker (tables, code fences, size limit)
  md_rag/embeddings.py        Ollama embeddings (chunks + questions, same model)
  md_rag/store.py             ChromaDB: open, upsert, delete, query
  md_rag/indexer.py           sync folders -> DB (new / changed / unchanged / deleted)
  md_rag/retriever.py         search(question) -> top-k chunks
  md_rag/chat.py              ask(question) -> answer + cited sources (Ollama chat model)
  md_rag/agent.py             router: docs question -> RAG, "I need an AWS account" -> intake
  md_rag/intake.py            asks the form fields step by step, validates, summary, confirm
  md_rag/validators.py        plain-Python rules (lengths, patterns, one email, person not team)
  md_rag/forms.py             loads a form definition from forms/*.yaml
  md_rag/servicenow.py        creates the ticket: fake (JSON file) | dry_run | live (not built yet)
  forms/aws_account.yaml      the AWS account form: fields, questions, hints, rules
  md_rag/langchain_loader.py  optional: same output as LangChain Documents
  scripts/index.py            build or update the vector DB
  scripts/search.py           ask a question, see the matching chunks
  scripts/ask.py              ask a question, get an answer with sources (or chat mode)
  scripts/agent.py            the agent chat: docs Q&A + AWS account requests
  scripts/inspect_db.py       what is stored in the DB
  scripts/check_embeddings.py health check: Ollama, vectors, meaning, DB, retrieval
  scripts/inspect_chunks.py   report of every chunk, no Ollama/Chroma needed
  tests/                      85 tests (pytest, no Ollama needed)
  data/chroma_db/             the vector DB (generated, git-ignored)
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

## Vector DB (needs Ollama running)

```bash
ollama serve                                   # in another terminal, if not already running
ollama pull qwen3-embedding:0.6b               # or the model set in config.py
python -m md_rag.embeddings                    # check: "dimension: 1024" for qwen3-embedding:0.6b

python -m scripts.index                        # embed + save everything
python -m scripts.index                        # run again: only changed files are re-embedded
python -m scripts.search "How do I activate the venv on Windows?"
python -m scripts.search "port already in use" -k 3 --source docs
python -m scripts.inspect_db --file guides/install.md
python -m scripts.index --reset                # wipe and rebuild (e.g. after changing the model)
python -m scripts.check_embeddings             # is embedding + retrieval working? PASS/WARN/FAIL
```

Each chunk's file hash is stored in its metadata, so re-indexing skips unchanged
files, replaces changed ones, and removes chunks of deleted files. A missing
folder is skipped and its chunks are kept.

## Ask questions (RAG answers)

```bash
ollama pull llama3.2:3b                                  # CHAT_MODEL in config.py
# ollama pull hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF # previous 1B model (commented out in config.py)
python -m scripts.ask "How do I activate the venv on Windows?"
python -m scripts.ask "What port does the API use?" --show-context   # see what the model was given
python -m scripts.ask                                     # chat mode, follow-ups remember context
python -m scripts.ask --model hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF "..."  # compare with the old 1B model
```

How an answer is made (`md_rag/chat.py`):

1. Search the vector DB for the top `ANSWER_TOP_K` chunks.
2. Drop chunks below `MIN_SIMILARITY`. If none are left, answer "I couldn't find that in
   your documents." without calling the chat model.
3. Add the other chunks of each matched section (`EXPAND_SECTIONS`), so a table that was
   split into pieces reaches the model complete (up to `MAX_CONTEXT_CHARS`).
4. Put the chunks in the last user message as `<passage id="1" ...>` blocks, then the
   question and a reminder: answer in your own words, cite `[1]`, don't repeat the passages.
5. Print the answer and the sources; `*` marks cited passages. If the model pasted the
   passages back instead of answering, a warning is printed.

Tune `MIN_SIMILARITY` with `scripts.search`: look at the similarity of good and bad
matches for a few questions and set it between them.

## AWS account request agent

```bash
python -m scripts.agent --requester you@company.com      # chat: questions + account requests
SERVICENOW_MODE=dry_run python -m scripts.agent          # show the payload, create nothing
python -m scripts.agent --tickets                         # list the fake tickets created so far
```

Say "I need a new AWS account" and the agent asks for each field in `forms/aws_account.yaml`
(Account Name, App/Team name, ServiceNow support group, Technical Owner, Budget Approver).
Answers are checked by `validators.py`; a bad answer is explained and asked again. Side
questions ("what is a support group?") are answered from your documents without losing the
answers so far. At the summary reply `yes`, `edit <n>` or `cancel`. In `fake` mode the
ticket is saved as `data/servicenow/RITM00100NN.json`.

The field just asked always takes the reply. Any other field is filled from the same
message only if the message names it (its `cues`, e.g. "technical owner", "budget") and
contains the value, so one email can't silently fill several fields.

To change the form, edit the YAML: add a field, change a question, hint, cue or rule. No code
change is needed. `live` mode needs the real instance URL, catalog item and credentials.

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
