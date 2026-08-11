from collections.abc import AsyncIterator
from datetime import UTC, datetime
from io import BytesIO
from typing import BinaryIO
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, ZipFile

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

import yitu.knowledge.artifacts as artifact_module
from yitu.identity.models import Role, User
from yitu.knowledge.artifacts import MinerUArtifactError, extract_mineru_archive
from yitu.knowledge.mineru_client import (
    MinerUPermanentError,
    MinerURetryableError,
    MinerUTask,
)
from yitu.knowledge.models import DocumentStatus, KnowledgeChunk, KnowledgeDocument
from yitu.knowledge.tasks import (
    PollOutcome,
    _poll_mineru_document,
    _submit_mineru_document,
)
from yitu.platform.database import SessionFactory, dispose_database


class FakeBlobStore:
    def __init__(self) -> None:
        self.presigned: list[tuple[str, int]] = []
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = (data, content_type)

    def open(self, key: str) -> BinaryIO:
        return BytesIO(self.objects[key][0])

    def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    def presign_get(self, key: str, expires_seconds: int = 900) -> str:
        self.presigned.append((key, expires_seconds))
        return "https://cos.test/document.pdf?signature=hidden"


class FakeMinerUClient:
    def __init__(
        self,
        *,
        task_id: str = "mineru-task-1",
        tasks: list[MinerUTask] | None = None,
        archive: bytes = b"",
        submit_error: Exception | None = None,
    ) -> None:
        self.task_id = task_id
        self.tasks = tasks or []
        self.archive = archive
        self.submit_error = submit_error
        self.submit_calls = 0
        self.polled_task_ids: list[str] = []

    async def submit(self, source_url: str) -> str:
        del source_url
        self.submit_calls += 1
        if self.submit_error is not None:
            raise self.submit_error
        return self.task_id

    async def get_task(self, task_id: str) -> MinerUTask:
        self.polled_task_ids.append(task_id)
        if not self.tasks:
            raise AssertionError("未配置 MinerU 轮询响应")
        return self.tasks.pop(0)

    async def download_result(self, url: str) -> bytes:
        del url
        return self.archive


def make_archive(files: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


@pytest_asyncio.fixture(autouse=True, loop_scope="function")
async def reset_database_pool() -> AsyncIterator[None]:
    await dispose_database()
    yield
    await dispose_database()


@pytest_asyncio.fixture(loop_scope="function")
async def queued_document() -> AsyncIterator[UUID]:
    user_id = uuid4()
    document_id = uuid4()
    now = datetime.now(UTC)
    async with SessionFactory() as session, session.begin():
        session.add(
            User(
                id=user_id,
                login_name=f"mineru-worker-{user_id}",
                display_name="MinerU Worker 测试用户",
                password_hash="not-used",
                role=Role.SYSTEM_ADMIN,
            )
        )
        session.add(
            KnowledgeDocument(
                id=document_id,
                filename="rule.pdf",
                content_type="application/pdf",
                size_bytes=10,
                sha256=uuid4().hex + uuid4().hex,
                object_key=f"documents/{document_id}.pdf",
                status=DocumentStatus.QUEUED,
                page_count=3,
                uploaded_by=user_id,
                parse_attempts=0,
                created_at=now,
                updated_at=now,
            )
        )

    yield document_id

    async with SessionFactory() as session, session.begin():
        await session.execute(
            delete(KnowledgeDocument).where(KnowledgeDocument.id == document_id)
        )
        await session.execute(delete(User).where(User.id == user_id))


def test_extract_archive_reads_markdown_without_writing_files() -> None:
    data = make_archive(
        {
            "result/full.md": "# 运输规则\n\n正文".encode(),
            "result/images/page-1.png": b"image",
        }
    )

    extracted = extract_mineru_archive(data)

    assert extracted.markdown.decode() == "# 运输规则\n\n正文"
    assert extracted.file_count == 2


@pytest.mark.parametrize(
    "unsafe_name",
    ["../full.md", "/full.md", "C:/full.md", "..\\full.md"],
)
def test_extract_archive_rejects_unsafe_paths(unsafe_name: str) -> None:
    with pytest.raises(MinerUArtifactError, match="unsafe path"):
        extract_mineru_archive(make_archive({unsafe_name: b"content"}))


def test_extract_archive_enforces_file_and_uncompressed_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(artifact_module, "MAX_ARCHIVE_FILES", 1)
    with pytest.raises(MinerUArtifactError, match="too many files"):
        extract_mineru_archive(make_archive({"full.md": b"ok", "image.png": b"x"}))

    monkeypatch.setattr(artifact_module, "MAX_ARCHIVE_FILES", 2)
    monkeypatch.setattr(artifact_module, "MAX_UNCOMPRESSED_BYTES", 3)
    with pytest.raises(MinerUArtifactError, match="uncompressed size"):
        extract_mineru_archive(make_archive({"full.md": b"four"}))


@pytest.mark.asyncio(loop_scope="function")
async def test_duplicate_submission_and_worker_restart_resume_polling(
    queued_document: UUID,
) -> None:
    store = FakeBlobStore()
    submit_client = FakeMinerUClient()

    assert await _submit_mineru_document(
        queued_document,
        store=store,
        client=submit_client,
    )
    assert await _submit_mineru_document(
        queued_document,
        store=store,
        client=submit_client,
    )
    assert submit_client.submit_calls == 1
    assert store.presigned == [(f"documents/{queued_document}.pdf", 900)]

    processing_client = FakeMinerUClient(
        tasks=[MinerUTask("mineru-task-1", "running", None, None)]
    )
    assert await _poll_mineru_document(
        queued_document,
        store=store,
        client=processing_client,
    ) == PollOutcome.PENDING

    archive = make_archive({"nested/full.md": "# 规则\n\n禁止倒置".encode()})
    restarted_client = FakeMinerUClient(
        tasks=[
            MinerUTask(
                "mineru-task-1",
                "done",
                "https://cdn.test/result.zip?signature=hidden",
                None,
            )
        ],
        archive=archive,
    )
    assert await _poll_mineru_document(
        queued_document,
        store=store,
        client=restarted_client,
    ) == PollOutcome.COMPLETED

    async with SessionFactory() as session:
        document = await session.get(KnowledgeDocument, queued_document)
        chunk_count = len(
            list(
                await session.scalars(
                    select(KnowledgeChunk).where(
                        KnowledgeChunk.document_id == queued_document
                    )
                )
            )
        )

    assert document is not None
    assert document.status == DocumentStatus.REVIEW_REQUIRED
    assert document.mineru_task_id == "mineru-task-1"
    assert document.source_artifact_key == f"documents/{queued_document}.pdf"
    assert document.parsed_text == "# 规则\n\n禁止倒置"
    assert document.parser_name == "mineru"
    assert document.parse_started_at is not None
    assert document.parse_finished_at is not None
    assert document.result_archive_key in store.objects
    assert document.markdown_artifact_key in store.objects
    assert store.objects[document.result_archive_key][1] == "application/zip"
    assert store.objects[document.markdown_artifact_key][1].startswith("text/markdown")
    assert processing_client.polled_task_ids == ["mineru-task-1"]
    assert restarted_client.polled_task_ids == ["mineru-task-1"]
    assert chunk_count == 1


@pytest.mark.asyncio(loop_scope="function")
async def test_temporary_submission_error_remains_retryable(
    queued_document: UUID,
) -> None:
    client = FakeMinerUClient(
        submit_error=MinerURetryableError("temporary failure")
    )

    with pytest.raises(MinerURetryableError):
        await _submit_mineru_document(
            queued_document,
            store=FakeBlobStore(),
            client=client,
        )

    async with SessionFactory() as session:
        document = await session.get(KnowledgeDocument, queued_document)
    assert document is not None
    assert document.status == DocumentStatus.QUEUED
    assert document.mineru_task_id is None


@pytest.mark.asyncio(loop_scope="function")
async def test_permanent_and_upstream_failures_enter_parse_failed(
    queued_document: UUID,
) -> None:
    permanent_client = FakeMinerUClient(
        submit_error=MinerUPermanentError("invalid request")
    )
    assert not await _submit_mineru_document(
        queued_document,
        store=FakeBlobStore(),
        client=permanent_client,
    )

    async with SessionFactory() as session, session.begin():
        document = await session.get(KnowledgeDocument, queued_document)
        assert document is not None
        assert document.status == DocumentStatus.PARSE_FAILED
        document.status = DocumentStatus.QUEUED
        document.error_message = None

    submit_client = FakeMinerUClient(task_id="mineru-task-failed")
    assert await _submit_mineru_document(
        queued_document,
        store=FakeBlobStore(),
        client=submit_client,
    )
    failed_client = FakeMinerUClient(
        tasks=[MinerUTask("mineru-task-failed", "failed", None, "upstream detail")]
    )
    assert await _poll_mineru_document(
        queued_document,
        store=FakeBlobStore(),
        client=failed_client,
    ) == PollOutcome.STOPPED

    async with SessionFactory() as session:
        document = await session.get(KnowledgeDocument, queued_document)
    assert document is not None
    assert document.status == DocumentStatus.PARSE_FAILED
    assert document.error_message == "MinerU parsing failed"
    assert document.parse_finished_at is not None
