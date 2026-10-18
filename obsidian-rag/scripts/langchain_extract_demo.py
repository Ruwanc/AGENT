"""Exploration: load + split the test note with LangChain, to compare with rag/chunking.py.

Run from the project root:
    python scripts/langchain_extract_demo.py sample_vault
"""
import sys
from collections import Counter

from langchain_community.document_loaders import ObsidianLoader
from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

vault = sys.argv[1] if len(sys.argv) > 1 else "sample_vault"

# 1. LOAD: one Document per .md file; frontmatter -> metadata, body -> page_content
docs = ObsidianLoader(vault, collect_metadata=True).load()
for d in docs:
    print("=== LOADED:", d.metadata["path"])
    for k, v in sorted(d.metadata.items()):
        print(f"   {k:<14} {v!r}"[:110])
    print("   body starts:", d.page_content[:60].replace("\n", " / "), "\n")

# 2. SPLIT BY HEADINGS: metadata gets H1..H6 keys (like your heading_path)
headers = [("#" * i, f"h{i}") for i in range(1, 7)]
md_splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers, strip_headers=True)

# 3. SPLIT LONG SECTIONS: paragraph -> line -> sentence -> word -> char (like split_long_section)
size_splitter = RecursiveCharacterTextSplitter(
    chunk_size=800, chunk_overlap=80,
    separators=["\n\n", "\n", ". ", " ", ""],
)

for doc in docs:
    sections = md_splitter.split_text(doc.page_content)
    for s in sections:                       # keep the file-level metadata on every chunk
        s.metadata = {**doc.metadata, **s.metadata}
    chunks = size_splitter.split_documents(sections)

    print(f"=== {doc.metadata['source']}: {len(sections)} sections -> {len(chunks)} chunks")
    for i, c in enumerate(chunks):
        path = " > ".join(c.metadata[f"h{n}"] for n in range(1, 7) if f"h{n}" in c.metadata)
        first = c.page_content[:45].replace("\n", " / ")
        print(f"{i:>2} {len(c.page_content):>4}  {path[:55]:<55} | {first}")
    print("chunk sizes:", sorted(Counter(len(c.page_content) // 100 * 100 for c in chunks).items()))
