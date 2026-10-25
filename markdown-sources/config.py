"""Settings for loading and chunking Markdown files.

SOURCES is a list of folders that contain .md files. Add one entry per folder
(a docs site, a repo's docs/ folder, a Confluence/Notion export, ...).
"""
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent

# Secrets (ServiceNow login) live in a local .env file next to this one, never in Git.
# Copy .env.example to .env and fill it in. Real environment variables win over .env.
try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_DIR / ".env")
except ImportError:          # python-dotenv not installed: plain environment variables still work
    pass

SOURCES = [
    {"name": "docs", "path": os.environ.get("DOCS_PATH", str(PROJECT_DIR / "sample_docs"))},
    # {"name": "work-docs", "path": "/Users/you/repos/platform/docs"},
]

# Folders skipped in every source
IGNORED_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "site", "_build", "dist"}
MARKDOWN_SUFFIXES = {".md", ".markdown"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}

# Frontmatter keys read as tags (docs tools use different names)
TAG_KEYS = ("tags", "tag", "keywords", "categories")

# chunking.py
MAX_CHUNK_CHARS = 800   # limit for the WHOLE chunk text, header line included
MIN_CHUNK_CHARS = 30

# embeddings.py (Ollama must be running: `ollama serve`)
# Pick ONE model. Changing it means: ollama pull <model>, then `python -m scripts.index --reset`.
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "qwen3-embedding:0.6b")
# EMBEDDING_MODEL = "hf.co/CompendiumLabs/bge-base-en-v1.5-gguf"
# EMBEDDING_MODEL = "mxbai-embed-large"
EMBED_BATCH_SIZE = 32

# Each model wants its own prefix on the QUESTION only (documents get none).
# The right one is picked automatically from EMBEDDING_MODEL, so the two can't get out of step.
_BGE_PREFIX = "Represent this sentence for searching relevant passages: "
QUERY_PREFIXES = {
    "qwen3-embedding": ("Instruct: Given a question, retrieve passages from the "
                        "documentation that answer it\nQuery: "),
    "bge-": _BGE_PREFIX,
    "mxbai-embed-large": _BGE_PREFIX,
}
QUERY_PREFIX = next((p for key, p in QUERY_PREFIXES.items() if key in EMBEDDING_MODEL), "")

# store.py (ChromaDB on disk; delete the folder or run `index --reset` to start over)
CHROMA_DIR = os.environ.get("CHROMA_DIR", str(PROJECT_DIR / "data" / "chroma_db"))
COLLECTION_NAME = "md_chunks"

# retriever.py
TOP_K = 5

# chat.py (answering questions with a local chat model in Ollama)
# Small models answer faster; bigger ones follow "use only the context" and cite sources better.
# Previous default (1B): fast, but weaker at sticking to the context and citing sources.
# CHAT_MODEL = os.environ.get("CHAT_MODEL", "hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF")
# Recommended (3B): better at "answer only from the passages" and [1] citations. Setup: ollama pull llama3.2:3b
CHAT_MODEL = os.environ.get("CHAT_MODEL", "llama3.2:3b")
# CHAT_MODEL = "qwen3:4b"
ANSWER_TOP_K = 4           # chunks given to the model as context
MIN_SIMILARITY = 0.45      # below this a chunk counts as "not relevant"; tune per embedding model
CHAT_TEMPERATURE = 0.1     # low = sticks to the text, less creative
HISTORY_TURNS = 3          # earlier Q&A pairs kept in interactive chat
EXPAND_SECTIONS = True     # also give the model the other chunks of a matched section
                           # (e.g. the rest of a table that was split into pieces)
MAX_CONTEXT_CHARS = 6000   # upper limit for all passages put in the prompt

# agent.py / intake.py / servicenow.py (AWS account requests)
ACCOUNT_FORM = PROJECT_DIR / "forms" / "aws_account.yaml"   # fields, questions and rules
EXTRACT_MODEL = os.environ.get("EXTRACT_MODEL", CHAT_MODEL)  # model that pulls values out of replies
REQUESTER_EMAIL = os.environ.get("REQUESTER_EMAIL", "")      # who is chatting; asked if empty
ALLOWED_EMAIL_DOMAINS = []                                    # e.g. ["sysco.com"]; empty = any domain
# fake    = save the ticket as a JSON file in data/servicenow/ and return a dummy RITM number
# dry_run = print what would be sent, create nothing
# live    = real ServiceNow REST API (settings below, secrets in .env)
SERVICENOW_MODE = os.environ.get("SERVICENOW_MODE", "fake")
SERVICENOW_FAKE_DIR = PROJECT_DIR / "data" / "servicenow"

# ---- live ServiceNow (only used when SERVICENOW_MODE=live). Values come from .env.
SN_INSTANCE = os.environ.get("SN_INSTANCE", "")            # e.g. https://yourcompanydev.service-now.com
SN_AUTH = os.environ.get("SN_AUTH", "basic")               # basic | oauth
SN_USERNAME = os.environ.get("SN_USERNAME", "")            # the service account
SN_PASSWORD = os.environ.get("SN_PASSWORD", "")
SN_CLIENT_ID = os.environ.get("SN_CLIENT_ID", "")          # oauth only
SN_CLIENT_SECRET = os.environ.get("SN_CLIENT_SECRET", "")  # oauth only
# catalog = order a Service Catalog item (best: runs the item's approvals and workflow)
# table   = insert a record straight into a table (simple; good for a first test)
SN_API = os.environ.get("SN_API", "catalog")
SN_CATALOG_ITEM_SYS_ID = os.environ.get("SN_CATALOG_ITEM_SYS_ID", "")   # catalog mode
SN_TABLE = os.environ.get("SN_TABLE", "incident")                       # table mode
SN_TIMEOUT = float(os.environ.get("SN_TIMEOUT", "30"))                  # seconds per call
