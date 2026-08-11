from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    text: str
    page_count: int
    parser_name: str
    parser_version: str


class DocumentParser(Protocol):
    def parse(self, data: bytes) -> ParsedDocument: ...


class PyMuPDFParser:
    """Lightweight fallback parser; production can replace it with PyMuPDF."""

    def parse(self, data: bytes) -> ParsedDocument:
        lines = [line.decode("utf-8", errors="ignore").strip() for line in data.splitlines()]
        text = "\n".join(line for line in lines if line and not line.startswith("%PDF"))
        pages = max(data.count(b"/Type /Page") - data.count(b"/Type /Pages"), 1)
        return ParsedDocument(text=text, page_count=pages, parser_name="pymupdf-fallback", parser_version="1")


class MinerUParser:
    def parse(self, data: bytes) -> ParsedDocument:
        raise RuntimeError("MinerU parser is not installed")
