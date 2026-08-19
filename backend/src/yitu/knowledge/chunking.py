import re
from dataclasses import dataclass

PAGE_MARKER_RE = re.compile(
    r"^\s*(?:<!--\s*(?:page|page_number)\s*:\s*(\d+)\s*-->|\[PAGE\s+(\d+)\s*\])\s*$",
    re.IGNORECASE,
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
# 法规「第X条」条号行（X 为阿拉伯或中文数字，可带尾随标点），用于识别
# 被空行从正文剥离的孤立条头，避免其单独成块、检索只命中条号而无正文。
CLAUSE_ONLY_RE = re.compile(r"第[0-9〇一二三四五六七八九十百零两]+条[、。：:，,\s]*")
# 法规「第X条」行（允许条号后跟同行的引导正文，如「第三条 本规定所称...主要包括：」）。
# 用于识别条款级 block 的起始，与 ENUMERATION_ITEM_RE 配合控制列举项合并的终止。
CLAUSE_HEAD_RE = re.compile(r"第[0-9〇一二三四五六七八九十百零两]+条\b")
# 条款条号行后跟引导语（如「主要包括：」「包括」「如下」），预示后续将出现列举项。
# 这种行后的空行不切分，等待 (一)(二)(三) 等列举项合并到同一 block。
CLAUSE_INTRO_RE = re.compile(
    r"第[0-9〇一二三四五六七八九十百零两]+条.*[:：]\s*$"
    r"|第[0-9〇一二三四五六七八九十百零两]+条.*(包括|包含|如下|下列)"
)
# 列举项开头：支持 (一)/(二)、（一）/（二）、1./2.、1、/2、、(1)/(2)、（1）/（2），
# 以及带右括号或点号尾随的形式。行首允许缩进，整行以列举标记开头即视为列举项。
# 命中后该行会与同一条款下其他列举项合并到同一 block，避免被空行切成碎片 chunk。
ENUMERATION_ITEM_RE = re.compile(
    r"^\s*(?:"
    r"\([0-9〇一二三四五六七八九十百零两]+\)"      # (一) (二) (1) (2)
    r"|[（][0-9〇一二三四五六七八九十百零两]+[）]"  # （一）（二）（1）（2）
    r"|[0-9]+[.、]"                              # 1. 2. 1、 2、
    r")"
)


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

    version = "markdown-v2"

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
                # 法规条号行（如「第四条」）后紧跟的空行不切分，让条头与后续
                # 正文合并到同一个块，避免产生「只有条号、没有内容」的碎片 chunk。
                if len(pending) == 1 and CLAUSE_ONLY_RE.fullmatch(pending[0].lstrip()):
                    index += 1
                    continue
                # 列举项之间的空行不切分：当 pending 末尾是列举项（(一)/(1)/1. 等），
                # 且后续仍可能有同条款下的列举项或子项时，保留 block 等待合并，
                # 避免条款下的子项被各自切成碎片 chunk。
                if self._pending_tail_is_enumeration(pending):
                    index += 1
                    continue
                # 条款条号 + 引导语（如「第三条 ... 主要包括：」）后跟空行也不切分，
                # 等待后续 (一)(二)(三) 列举项合并到同一 block，避免条头孤立成块。
                if pending and CLAUSE_INTRO_RE.match(pending[-1].strip()):
                    index += 1
                    continue
                flush()
                index += 1
                continue
            else:
                # 非空非表格行：若当前 block 处于列举/条款引导态，且新行既不是
                # 列举项、也不是同一条款的条号延续，则结束 block，避免把后续
                # 无关正文（如下一条「第X条」）吞进列举块。
                if self._pending_tail_is_enumeration(pending) or (
                    pending and CLAUSE_INTRO_RE.match(pending[-1].strip())
                ):
                    if not ENUMERATION_ITEM_RE.match(line) and not CLAUSE_HEAD_RE.match(line):
                        flush()
                    elif CLAUSE_HEAD_RE.match(line) and not CLAUSE_INTRO_RE.match(line.strip()):
                        # 新「第X条」条头：若本身不含列举引导语，作为新条款起始，
                        # 结束当前列举 block。
                        flush()
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

    @staticmethod
    def _pending_tail_is_enumeration(pending: list[str]) -> bool:
        """判断 pending 末尾是否为列举项，用于决定空行是否触发合并。

        只看末行而非整段，确保「条头 + 引导语 + 列举项」组合也能被识别：
        当末行是 (一)/(1)/1. 等列举项开头时，后续空行应跳过，等待同条款
        下的下一个列举项或子项正文合并到同一 block。
        """
        if not pending:
            return False
        return bool(ENUMERATION_ITEM_RE.match(pending[-1].lstrip()))

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
