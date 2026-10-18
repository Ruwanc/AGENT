"""Optional LangChain adapter: the same sources, as LangChain Documents.

Uses this project's loader + chunker (they handle frontmatter, tables and
heading context better than TextLoader/DirectoryLoader), then wraps the result
in langchain_core Documents so you can plug it into langchain-chroma,
retrievers or LangGraph later.

    from md_rag.langchain_loader import load_documents, load_chunks
"""
from langchain_core.documents import Document

from config import SOURCES
from md_rag.chunking import chunk_note
from md_rag.sources import chunk_id, chunk_metadata, load_all


def load_documents(sources=SOURCES):
    """One Document per file (cleaned body, frontmatter in metadata)."""
    return [
        Document(
            page_content=doc["body"],
            metadata={**doc["metadata"], "source": doc["source"], "note_path": doc["path"],
                      "title": doc["title"], "tags": ",".join(doc["tags"]), "hash": doc["hash"]},
            id=f"{doc['source']}:{doc['path']}",
        )
        for doc in load_all(sources)
    ]


def load_chunks(sources=SOURCES):
    """One Document per chunk, ready for a vector store (ids are deterministic)."""
    out = []
    for doc in load_all(sources):
        for chunk in chunk_note(doc):
            out.append(Document(
                page_content=chunk["text"],
                metadata=chunk_metadata(doc, chunk),
                id=chunk_id(chunk, doc["source"]),
            ))
    return out


if __name__ == "__main__":
    chunks = load_chunks()
    print(f"{len(chunks)} LangChain Documents")
    for d in chunks[:5]:
        print(d.id, "|", d.page_content[:70].replace("\n", " / "))
