"""Heading-aware chunking for Markdown notes.

Pure text processing: strings in, lists of dicts out. No files, no Ollama, no Chroma.
"""
import re

from config import MAX_CHUNK_CHARS, MIN_CHUNK_CHARS

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")   # "## Diet"; "#tag" has no space, so it is not a heading
FENCE_RE = re.compile(r"^\s*(```|~~~)")              # start/end of a fenced code block
PARAGRAPH_RE = re.compile(r"\n\s*\n")                # blank line(s) between paragraphs
SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")           # whitespace after . ! ?


def split_by_headings(body, title=""):
    """Split a note body into (heading_path, text) sections.

    heading_path looks like "Cats > Diet > Treats". Text before the first
    heading gets `title` as its path. Empty sections are dropped.
    """
    sections = []
    stack = []        # [(level, heading_text), ...] for the current position
    buffer = []       # lines of the section being built
    in_fence = False

    def flush():
        text = "\n".join(buffer).strip()
        if text:
            path = " > ".join(h for _, h in stack) or title
            sections.append((path, text))
        buffer.clear()

    for line in body.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            buffer.append(line)
            continue

        match = None if in_fence else HEADING_RE.match(line)
        if match:
            flush()
            level = len(match.group(1))
            while stack and stack[-1][0] >= level:   # leaving deeper/equal sections
                stack.pop()
            stack.append((level, match.group(2)))
        else:
            buffer.append(line)

    flush()
    return sections


def _split_oversized(paragraph, max_chars):
    """Split one too-long paragraph on sentences; hard-split a sentence only as a last resort."""
    pieces, current = [], ""
    for sentence in SENTENCE_RE.split(paragraph):
        while len(sentence) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence[:max_chars])
            sentence = sentence[max_chars:]

        candidate = f"{current} {sentence}" if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
        else:
            pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    return pieces


def _is_table(paragraph):
    """True if every line of the paragraph starts with '|' (a Markdown table)."""
    lines = paragraph.splitlines()
    return len(lines) >= 2 and all(line.lstrip().startswith("|") for line in lines)


def _split_table(table, max_chars):
    """Split a table between rows, repeating the header and |---| lines in every piece."""
    lines = table.splitlines()
    header = "\n".join(lines[:2])
    pieces, current = [], header
    for row in lines[2:]:
        candidate = f"{current}\n{row}"
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current != header:            # never emit a header-only piece
                pieces.append(current)
            current = f"{header}\n{row}"
    if current != header:
        pieces.append(current)
    return pieces


def split_long_section(text, max_chars=MAX_CHUNK_CHARS):
    """Pack paragraphs into pieces of at most max_chars characters."""
    if len(text) <= max_chars:
        return [text]

    pieces, current = [], ""
    for paragraph in PARAGRAPH_RE.split(text):
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        if len(paragraph) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            if _is_table(paragraph):
                pieces.extend(_split_table(paragraph, max_chars))
            else:
                pieces.extend(_split_oversized(paragraph, max_chars))
            continue

        candidate = f"{current}\n\n{paragraph}" if current else paragraph
        if len(candidate) <= max_chars:
            current = candidate
        else:                       # current is non-empty here, otherwise candidate would fit
            pieces.append(current)
            current = paragraph

    if current:
        pieces.append(current)
    return pieces


def chunk_note(note, max_chars=MAX_CHUNK_CHARS, min_chars=MIN_CHUNK_CHARS):
    """Turn a note dict ({"path", "title", "tags", "body"}) into a list of chunk dicts.

    The chunk "text" is prefixed with "title > heading path" so that a chunk
    like "Give 5 mg twice daily" still carries its context when embedded.
    """
    title = note.get("title", "")
    chunks = []

    for heading_path, section_text in split_by_headings(note["body"], title):
        for piece in split_long_section(section_text, max_chars):
            if len(piece) < min_chars:
                continue

            if not title or heading_path.startswith(title):
                header = heading_path
            else:
                header = f"{title} > {heading_path}"

            chunks.append({
                "text": f"{header}\n\n{piece}",
                "note_path": note["path"],
                "heading_path": heading_path,
                "tags": note.get("tags", []),
                "chunk_index": len(chunks),
            })
    return chunks


if __name__ == "__main__":
    demo = {
        "path": "Pets/Cats.md",
        "title": "Cats",
        "tags": ["pets"],
        "body": "Intro about cats and why people keep them.\n\n# Cats\n## Diet\nCats are obligate carnivores and need meat.\n### Treats\nTuna is a popular treat but should be limited.\n## Health\nAnnual vaccines are recommended by vets.\n",
    }
    for c in chunk_note(demo):
        print(c["chunk_index"], "|", c["heading_path"], "|", c["text"].replace("\n", " / "))
