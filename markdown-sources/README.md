# CET Agent

A local agent with two jobs, in one chat:

1. **Docs Q&A (RAG):** loads, chunks and embeds plain Markdown files into a local ChromaDB
   (embeddings and answers from models served by Ollama), then answers questions with sources.
2. **AWS account requests:** say "I need a new AWS account"; it asks for each field, checks
   the answers and creates a ServiceNow ticket (fake, dry run or live).

```
cet-agent/
├── README.md · requirements.txt · .env.example · .gitignore
├── .env                        ServiceNow secrets (git-ignored, never commit)
├── .streamlit/config.toml      UI settings
├── config.py                   all settings: folders, models, chunk sizes, ServiceNow mode
│
├── cet_agent/                  the Python package
│   ├── rag/                    documents -> answers
│   │   ├── sources.py          list files, frontmatter, cleaning, tags, titles, IDs, metadata
│   │   ├── chunking.py         heading-aware chunker (tables, code fences, size limit)
│   │   ├── embeddings.py       Ollama embeddings (chunks + questions, same model)
│   │   ├── store.py            ChromaDB: open, upsert, delete, query
│   │   ├── indexer.py          sync folders -> DB (new / changed / unchanged / deleted)
│   │   ├── retriever.py        search(question) -> top-k chunks, section expansion
│   │   ├── chat.py             ask(question) -> answer + cited sources
│   │   └── langchain_loader.py optional: same output as LangChain Documents
│   ├── agent/                  conversation + requests
│   │   ├── router.py           docs question -> RAG, "I need an AWS account" -> intake
│   │   ├── intake.py           asks the form fields step by step, validates, summary, confirm
│   │   ├── forms.py            loads a form definition from forms/*.yaml
│   │   └── validators.py       plain-Python rules (lengths, patterns, one email, person not team)
│   └── integrations/
│       └── servicenow.py       creates the ticket: fake (JSON file) | dry_run | live (REST API)
│
├── forms/aws_account.yaml      the AWS account form: fields, questions, hints, rules
├── docs/                       what the RAG indexes (config.SOURCES)
│   ├── company/                your real documents (tags.md, ...)
│   └── samples/                learning/test files (README, guides/install.md, chunking-test.md)
├── originals/                  old versions kept for reference, not indexed (labels.md)
├── ui/chat_app.py              browser chat "CET Agent" (streamlit run ui/chat_app.py)
├── scripts/                    command-line tools, run as python -m scripts.<name>
│   ├── index.py                build or update the vector DB
│   ├── search.py · ask.py      matching chunks · answers with sources (or chat mode)
│   ├── agent.py                terminal chat: docs Q&A + AWS account requests
│   ├── inspect_db.py · inspect_chunks.py      what is stored · every chunk (no Ollama)
│   └── check_embeddings.py · check_servicenow.py   health checks
├── tests/                      99 tests (pytest, no Ollama or ServiceNow needed)
│   ├── rag/                    sources, chunking, store, chat
│   └── agent/                  intake/router, live ServiceNow client (fake HTTP)
└── data/                       generated, git-ignored: chroma_db/, servicenow/ (fake tickets)
```

How the parts connect:

```
          ui/chat_app.py    scripts/agent.py
                   \           /
                    ▼         ▼
                 agent/router.py
                 /             \
       docs question         AWS account request
            ▼                       ▼
       rag/chat.py           agent/intake.py ◄── forms/*.yaml, agent/validators.py
            ▼                       ▼
       rag/retriever.py      integrations/servicenow.py ──► ServiceNow
            ▼
       rag/store.py (ChromaDB) ◄── rag/indexer.py ◄── rag/chunking.py ◄── rag/sources.py ◄── docs/
```

## Run (macOS / Linux)

```bash
cd ~/MyLearning/AGENT
source .venv/bin/activate
pip install -r cet-agent/requirements.txt
cd cet-agent
pytest -q
python -m cet_agent.rag.sources                 # one line per loaded file
python -m scripts.inspect_chunks         # every chunk
python -m scripts.inspect_chunks samples --full
python -m cet_agent.rag.langchain_loader        # LangChain Documents
```

## Vector DB (needs Ollama running)

```bash
ollama serve                                   # in another terminal, if not already running
ollama pull qwen3-embedding:0.6b               # or the model set in config.py
python -m cet_agent.rag.embeddings                    # check: "dimension: 1024" for qwen3-embedding:0.6b

python -m scripts.index                        # embed + save everything
python -m scripts.index                        # run again: only changed files are re-embedded
python -m scripts.search "How do I activate the venv on Windows?"
python -m scripts.search "port already in use" -k 3 --source samples
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

How an answer is made (`cet_agent/rag/chat.py`):

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
change is needed.

## Chat in the browser (simple UI)

```bash
pip install -r requirements.txt          # adds streamlit
streamlit run ui/chat_app.py             # opens http://localhost:8501
AGENT_UI_DEMO=1 streamlit run ui/chat_app.py   # try the screens without Ollama
```

The same agent as `scripts.agent`, in a chat page: ask about your documents (answers stream
in, sources are under "Sources"), or say "I need a new AWS account". The sidebar sets your
email, the ServiceNow mode (fake / dry_run / live) and the chat model; click *New
conversation* after changing them. Run it from the project root so `.streamlit/config.toml`
is used (no usage statistics sent, only reachable from your own computer).

**Logo:** save your logo as `ui/logo.png` (or `.jpg` / `.svg`; a square image looks best).
It replaces the tab icon, the sidebar and title icon, and the agent's chat avatar. Restart
Streamlit after adding it. Without the file, emoji icons are used.

## Connect to the real ServiceNow (live mode)

**1. Put the service account in `.env`** (git-ignored; never commit it or paste it into a chat):

```bash
cp .env.example .env      # then edit .env: SN_INSTANCE, SN_USERNAME, SN_PASSWORD, SN_API, ...
pip install -r requirements.txt     # adds requests + python-dotenv
```

**2. Choose how tickets are created** (`SN_API` in `.env`):

| SN_API | What it calls | Use when |
|---|---|---|
| `catalog` (recommended) | `POST /api/sn_sc/servicecatalog/items/{SN_CATALOG_ITEM_SYS_ID}/order_now` | There is (or will be) an "AWS account request" catalog item. Creates REQ + RITM and runs its approvals. |
| `table` | `POST /api/now/table/{SN_TABLE}` | First smoke test, or no catalog item yet. Values go into the description. |

Catalog item sys_id: open the item in ServiceNow → right-click the header → *Copy sys_id*.

**3. Check the connection (creates nothing):**

```bash
python -m scripts.check_servicenow --email you@company.com
```

It tests login, a user lookup and the catalog item, and lists the item's real variable
names. Copy those into the `servicenow:` lines of `forms/aws_account.yaml`. If a variable is a
user Reference (type 8), add `servicenow_ref: sys_user` to that field so the agent sends the
user's sys_id instead of the email text.

**4. Run it:** try `SERVICENOW_MODE=dry_run` first, then
`SERVICENOW_MODE=live python -m scripts.agent`. Use a dev/test instance before production.

**What the service account needs** (ask the ServiceNow admins):
- REST API access (web service access; not SSO-only, so basic or OAuth login works)
- read on `sys_user` (email lookup) and `sc_req_item` (to get the RITM number)
- permission to order the catalog item for someone else (catalog mode, `sysparm_requested_for`), or create on `SN_TABLE` (table mode)
- for OAuth (`SN_AUTH=oauth`): an Application Registry client id/secret

Errors (wrong password, missing role, wrong sys_id, VPN down, timeout) are shown in the chat
and your answers are kept, so you can fix `.env` and reply `yes` again. After a **timeout**,
check ServiceNow first: the request may have been created.

## Add your own folders

Edit `SOURCES` in `config.py` (or set `DOCS_PATH` to replace `docs/company`):

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
