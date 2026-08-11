from dataclasses import dataclass
from typing import Protocol

from yitu.knowledge.artifacts import MinerUArtifactError


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    text: str
    page_count: int
    parser_name: str
    parser_version: str


class DocumentParser(Protocol):
    def parse(self, data: bytes) -> ParsedDocument: ...


class PyMuPDFParser:
    """开发环境的轻量 PDF 降级解析器，不参与生产 MinerU 主链路。"""

    def parse(self, data: bytes) -> ParsedDocument:
        lines = [line.decode("utf-8", errors="ignore").strip() for line in data.splitlines()]
        text = "\n".join(line for line in lines if line and not line.startswith("%PDF"))
        pages = max(data.count(b"/Type /Page") - data.count(b"/Type /Pages"), 1)
        return ParsedDocument(text=text, page_count=pages, parser_name="pymupdf-fallback", parser_version="1")


class MinerUParser:
    """把 MinerU 生成的 UTF-8 Markdown 转为统一解析结果。"""

    def parse(self, data: bytes) -> ParsedDocument:
        try:
            text = data.decode("utf-8").lstrip("\ufeff").strip()
        except UnicodeDecodeError:
            raise MinerUArtifactError("MinerU full.md is not valid UTF-8") from None
        if not text:
            raise MinerUArtifactError("MinerU full.md is empty")
        return ParsedDocument(
            text=text,
            page_count=1,
            parser_name="mineru",
            parser_version="v4-vlm",
        )
