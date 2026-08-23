import re
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol
from xml.etree import ElementTree
from zipfile import BadZipFile, ZipFile

from yitu.knowledge.artifacts import MinerUArtifactError


@dataclass(frozen=True, slots=True)
class ParsedDocument:
    text: str
    page_count: int
    parser_name: str
    parser_version: str


class DocumentParser(Protocol):
    def parse(self, data: bytes) -> ParsedDocument: ...


class DocumentParseError(ValueError):
    """表示源文档无法解析，不应重试。"""


def decode_text(data: bytes) -> str:
    """按 UTF-8 优先、GB18030 兜底解码纯文本源文件（md/txt）。"""
    for encoding in ("utf-8", "gb18030"):
        try:
            return data.decode(encoding).lstrip("\ufeff").strip()
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace").strip()


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


class PlainTextParser:
    """把 md/txt 源文件解码为统一解析结果，不经过 MinerU。"""

    def __init__(self, parser_name: str) -> None:
        self.parser_name = parser_name

    def parse(self, data: bytes) -> ParsedDocument:
        text = decode_text(data)
        if not text:
            raise DocumentParseError("document has no decodable text")
        return ParsedDocument(
            text=text,
            page_count=1,
            parser_name=self.parser_name,
            parser_version="1",
        )


_W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def _wtag(local: str) -> str:
    return f"{{{_W_NS}}}{local}"


class DocxParser:
    """把 .docx 源文件提取为 Markdown 风格文本，零外部依赖。

    只解析 word/document.xml 的段落文本，并将标题样式（Heading1/标题1 等）
    映射为 Markdown 标题，让下游 markdown-v4 分块器能识别章节结构。
    """

    def parse(self, data: bytes) -> ParsedDocument:
        text = self._extract(data)
        if not text:
            raise DocumentParseError("docx has no extractable text")
        return ParsedDocument(
            text=text,
            page_count=1,
            parser_name="docx",
            parser_version="1",
        )

    def _extract(self, data: bytes) -> str:
        try:
            archive = ZipFile(BytesIO(data))
        except BadZipFile:
            raise DocumentParseError("docx is not a valid zip archive") from None
        with archive:
            try:
                document_xml = archive.read("word/document.xml")
            except KeyError:
                raise DocumentParseError("docx is missing word/document.xml") from None

        try:
            root = ElementTree.fromstring(document_xml)
        except ElementTree.ParseError:
            raise DocumentParseError("docx document.xml is malformed") from None

        body = root.find(_wtag("body"))
        if body is None:
            raise DocumentParseError("docx has no body")

        lines: list[str] = []
        for para in body.iter(_wtag("p")):
            level = self._heading_level(para)
            text = "".join(node.text or "" for node in para.iter(_wtag("t"))).strip()
            if not text:
                continue
            lines.append(f"{'#' * level} {text}" if level else text)
        return "\n\n".join(lines)

    def _heading_level(self, para: ElementTree.Element) -> int | None:
        ppr = para.find(_wtag("pPr"))
        if ppr is None:
            return None
        pstyle = ppr.find(_wtag("pStyle"))
        if pstyle is None:
            return None
        value = (pstyle.get(_wtag("val")) or "").lower()
        match = re.search(r"(?:heading|标题)\s*(\d)", value)
        if not match:
            return None
        return min(max(int(match.group(1)), 1), 6)
