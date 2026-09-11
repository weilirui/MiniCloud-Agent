"""Document chunking strategies."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Chunk:
    """A text chunk."""

    text: str
    index: int
    metadata: dict


def chunk_text(
    text: str,
    chunk_size: int = 800,
    chunk_overlap: int = 100,
) -> list[Chunk]:
    """Recursive character chunking with paragraph/line/sentence boundaries.

    Splits on: \\n\\n > \\n > 。/!/? > spaces > chars
    """
    if not text or not text.strip():
        return []

    separators = ["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""]

    chunks: list[Chunk] = []
    parts = _recursive_split(text, separators, chunk_size)

    cursor = 0
    for i, part in enumerate(parts):
        part = part.strip()
        if not part:
            continue
        chunks.append(Chunk(text=part, index=i, metadata={
            "char_start": cursor,
            "char_end": cursor + len(part),
        }))
        cursor += len(part)

    # Apply overlap by merging trailing context
    if chunk_overlap > 0 and len(chunks) > 1:
        overlapped: list[Chunk] = [chunks[0]]
        for c in chunks[1:]:
            prev = overlapped[-1].text
            tail = prev[-chunk_overlap:] if len(prev) > chunk_overlap else prev
            new_text = tail + c.text
            if len(new_text) > chunk_size * 1.5:
                # Overlap would make chunk too long, skip
                overlapped.append(c)
            else:
                overlapped.append(Chunk(
                    text=new_text,
                    index=len(overlapped),
                    metadata=c.metadata,
                ))
        # Re-index
        for i, c in enumerate(overlapped):
            c.index = i
        chunks = overlapped

    return chunks


def _recursive_split(text: str, separators: list[str], chunk_size: int) -> list[str]:
    """Split text using the first separator that produces chunks <= chunk_size."""
    if len(text) <= chunk_size or not separators:
        return [text]

    sep = separators[0]
    rest_seps = separators[1:]

    if sep == "":
        # Hard split by char count
        return [text[i:i + chunk_size] for i in range(0, len(text), chunk_size)]

    splits = text.split(sep)
    if len(splits) == 1:
        return _recursive_split(text, rest_seps, chunk_size)

    # Recombine small pieces
    parts: list[str] = []
    current = ""
    for s in splits:
        candidate = (current + sep + s) if current else s
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                parts.append(current)
            if len(s) > chunk_size:
                parts.extend(_recursive_split(s, rest_seps, chunk_size))
                current = ""
            else:
                current = s
    if current:
        parts.append(current)
    return parts


def detect_file_type(filename: str, content: bytes | None = None) -> str:
    """Detect file type from filename/content. Returns: markdown/code/text/pdf."""
    name = filename.lower()
    if name.endswith(".md") or name.endswith(".markdown"):
        return "markdown"
    if name.endswith((".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
                     ".c", ".cpp", ".h", ".hpp", ".rb", ".php", ".sh", ".bash",
                     ".yaml", ".yml", ".json", ".toml", ".xml", ".html", ".css",
                     ".scss", ".vue", ".svelte")):
        return "code"
    if name.endswith(".pdf"):
        return "pdf"
    return "text"


def load_file_content(filename: str, content: bytes) -> str:
    """Read file content as text, with PDF support."""
    ftype = detect_file_type(filename, content)
    if ftype == "pdf":
        try:
            from pypdf import PdfReader
            import io
            reader = PdfReader(io.BytesIO(content))
            return "\n\n".join(p.extract_text() or "" for p in reader.pages)
        except Exception as e:
            raise ValueError(f"PDF parse failed: {e}")
    # text-based
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            import chardet
            detected = chardet.detect(content)
            return content.decode(detected.get("encoding") or "utf-8", errors="replace")
        except Exception:
            return content.decode("utf-8", errors="replace")