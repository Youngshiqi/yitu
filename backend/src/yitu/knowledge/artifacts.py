from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import BadZipFile, ZipFile, ZipInfo

MAX_ARCHIVE_BYTES = 200 * 1024 * 1024
MAX_ARCHIVE_FILES = 2_000
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024


class MinerUArtifactError(ValueError):
    """表示 MinerU 产物不完整或违反安全限制，不应重试。"""


@dataclass(frozen=True, slots=True)
class ExtractedMinerUArchive:
    """保存安全校验后读取的 Markdown 和归档文件数量。"""

    markdown: bytes
    file_count: int


def _safe_member_path(info: ZipInfo) -> PurePosixPath:
    # ZIP 文件名可能使用 Windows 分隔符，统一后再检查路径穿越。
    normalized = info.filename.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or path.is_absolute()
        or ".." in path.parts
        or (path.parts and ":" in path.parts[0])
    ):
        raise MinerUArtifactError("MinerU archive contains an unsafe path")
    return path


def extract_mineru_archive(data: bytes) -> ExtractedMinerUArchive:
    """校验 MinerU ZIP，并只在内存中读取唯一的 `full.md`。"""
    if len(data) > MAX_ARCHIVE_BYTES:
        raise MinerUArtifactError("MinerU archive exceeds the size limit")

    try:
        archive = ZipFile(BytesIO(data))
    except BadZipFile:
        raise MinerUArtifactError("MinerU result is not a valid ZIP archive") from None

    with archive:
        members = archive.infolist()
        if len(members) > MAX_ARCHIVE_FILES:
            raise MinerUArtifactError("MinerU archive contains too many files")

        total_size = 0
        markdown_members: list[ZipInfo] = []
        for info in members:
            path = _safe_member_path(info)
            total_size += info.file_size
            if total_size > MAX_UNCOMPRESSED_BYTES:
                raise MinerUArtifactError(
                    "MinerU archive exceeds the uncompressed size limit"
                )
            if not info.is_dir() and path.name == "full.md":
                markdown_members.append(info)

        if len(markdown_members) != 1:
            raise MinerUArtifactError(
                "MinerU archive must contain exactly one full.md"
            )

        try:
            markdown = archive.read(markdown_members[0])
        except (BadZipFile, RuntimeError):
            raise MinerUArtifactError("MinerU full.md cannot be read safely") from None

    return ExtractedMinerUArchive(markdown=markdown, file_count=len(members))
