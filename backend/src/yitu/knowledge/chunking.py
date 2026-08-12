import re
from dataclasses import dataclass

PAGE_MARKER_RE = re.compile(
    r"^\s*(?:<!--\s*(?:page|page_number)\s*:\s*(\d+)\s*-->|\[PAGE\s+(\d+)\s*\])\s*$",
    re.IGNORECASE,
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


@dataclass(frozen=True, slots=True)
class TextChunk:
    """保留章节、内容类型和页码的可向量化知识块。"""

    index: int
    content: str
    title: str | None = None
    section_path: tuple[str, ...] = ()
    content_type: str = "paragraph"
    page_start: int | None = None
    page_end: int | None = None


class ChunkingPolicy:
    """按 Markdown 结构优先切片，长段落再按字符上限重叠切分。"""

    version = "markdown-v1"

    def __init__(self, max_chars: int = 800, overlap: int = 100) -> None:
        if max_chars <= 0 or overlap < 0 or overlap >= max_chars:
            raise ValueError("invalid chunking policy")
        self.max_chars = max_chars
        self.overlap = overlap

    def chunk(self, text: str) -> list[TextChunk]:
        """解析标题、表格和页码标记，返回稳定顺序的知识块。"""
        lines = [line.rstrip() for line in text.replace("\r\n", "\n").split("\n")]
        blocks: list[tuple[str, str, tuple[str, ...], int | None, int | None]] = []
        headings: list[str] = []
        pending: list[str] = []
        block_type = "paragraph"
        block_start_page: int | None = None
        current_page: int | None = None

        def flush() -> None:
            nonlocal pending, block_type, block_start_page
            content = self._normalize_lines(pending)
            if content:
                blocks.append(
                    (
                        content,
                        block_type,
                        tuple(headings),
                        block_start_page,
                        current_page or block_start_page,
                    )
                )
            pending = []
            block_type = "paragraph"
            block_start_page = None

        index = 0
        while index < len(lines):
            line = lines[index]
            page_match = PAGE_MARKER_RE.match(line)
            if page_match:
                current_page = int(page_match.group(1) or page_match.group(2))
                index += 1
                continue
            heading_match = HEADING_RE.match(line)
            if heading_match:
                flush()
                level = len(heading_match.group(1))
                headings = headings[: level - 1]
                headings.append(heading_match.group(2).strip())
                index += 1
                continue
            if self._is_table_line(line):
                if pending and block_type != "table":
                    flush()
                block_type = "table"
            elif not line.strip():
                flush()
                index += 1
                continue
            if block_start_page is None:
                block_start_page = current_page
            pending.append(line)
            index += 1
        flush()

        chunks: list[TextChunk] = []
        for content, content_type, section_path, page_start, page_end in blocks:
            title = section_path[-1] if section_path else None
            for fragment in self._split(content):
                chunks.append(
                    TextChunk(
                        index=len(chunks),
                        content=fragment,
                        title=title,
                        section_path=section_path,
                        content_type=content_type,
                        page_start=page_start,
                        page_end=page_end,
                    )
                )
        return chunks

    @staticmethod
    def _normalize_lines(lines: list[str]) -> str:
        return re.sub(r"[ \t]+", " ", "\n".join(lines)).strip()

    @staticmethod
    def _is_table_line(line: str) -> bool:
        return line.lstrip().startswith("|") and line.rstrip().endswith("|")

    def _split(self, content: str) -> list[str]:
        if len(content) <= self.max_chars:
            return [content]
        fragments: list[str] = []
        start = 0
        while start < len(content):
            end = min(start + self.max_chars, len(content))
            if end < len(content):
                boundary = max(
                    content.rfind("。", start, end),
                    content.rfind("\n", start, end),
                )
                if boundary > start + self.max_chars // 2:
                    end = boundary + 1
            fragments.append(content[start:end].strip())
            if end == len(content):
                break
            start = max(end - self.overlap, start + 1)
        return fragments
