"""Settings for loading and chunking Markdown files.

SOURCES is a list of folders that contain .md files. Add one entry per folder
(a docs site, a repo's docs/ folder, a Confluence/Notion export, ...).
"""
import os
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent

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
