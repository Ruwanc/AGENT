# Settings are added here as you build each file.
import os

# chunking.py
MAX_CHUNK_CHARS = 800
MIN_CHUNK_CHARS = 30

# embeddings.py
EMBEDDING_MODEL = "hf.co/CompendiumLabs/bge-base-en-v1.5-gguf"
EMBED_BATCH_SIZE = 32
# BGE models work best when the *query* (not the documents) has this prefix.
# Check the model card of the exact model you use; set to "" if it needs none.
QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

# vault.py
VAULT_PATH = os.environ.get("VAULT_PATH", "/path/to/your/ObsidianVault")  # per-device: set env var VAULT_PATH
IGNORED_DIRS = {".obsidian", ".trash", ".git"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp"}
