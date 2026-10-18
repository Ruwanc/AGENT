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
