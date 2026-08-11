import re
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TextChunk:
    index: int
    content: str
    page_start: int | None = None
    page_end: int | None = None


class ChunkingPolicy:
    def __init__(self, max_chars: int = 800, overlap: int = 100) -> None:
        if max_chars <= 0 or overlap < 0 or overlap >= max_chars:
            raise ValueError("invalid chunking policy")
        self.max_chars = max_chars
        self.overlap = overlap

    def chunk(self, text: str) -> list[TextChunk]:
        normalized = re.sub(r"\s+", " ", text).strip()
        if not normalized:
            return []
        chunks: list[TextChunk] = []
        start = 0
        while start < len(normalized):
            end = min(start + self.max_chars, len(normalized))
            if end < len(normalized):
                boundary = normalized.rfind("。", start, end)
                if boundary > start + self.max_chars // 2:
                    end = boundary + 1
            chunks.append(TextChunk(len(chunks), normalized[start:end]))
            if end == len(normalized):
                break
            start = end - self.overlap
        return chunks
