# obsidian-rag

Local RAG over an Obsidian vault: Python + ChromaDB + Ollama. Project history and plan: `HANDOFF.md`.

## Set up on a new device

1. Install Python 3.10+, Git, and [Ollama](https://ollama.com).
2. Pull the models (once per device):
   ```bash
   ollama pull hf.co/CompendiumLabs/bge-base-en-v1.5-gguf
   ollama pull hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF
   ```
3. Get the code: `git clone <your-repo-url> obsidian-rag && cd obsidian-rag`
4. Create a virtual environment and install dependencies:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate        # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```
5. Point at this device's vault (the path differs per machine):
   ```bash
   export VAULT_PATH="/home/me/ObsidianVault"     # Windows PowerShell: $env:VAULT_PATH="C:\Vault"
   ```
6. Check: `pytest -q` and `python -m rag.embeddings`.

`data/` (ChromaDB + manifest) is generated and git-ignored: never copy it between
devices, just re-index on each one.

## Status

| Phase | File | State |
|---|---|---|
| 0 | environment | done |
| 1 | `rag/vault.py` | **in progress**: make `pytest tests/test_vault.py` pass |
| 2 | `rag/chunking.py` | done (12 tests) |
| 3 | `rag/embeddings.py` | done; `rag/store.py` next |
| 4-8 | retriever, chat, indexer, watcher, hardening | to do |
