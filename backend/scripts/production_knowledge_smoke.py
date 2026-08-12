"""运行生产 RAG 的固定适配器旅程，不依赖 pytest 或真实第三方密钥。"""

import asyncio
import json
import shutil
import tempfile
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import delete, select

from yitu.demo.seed import seed_demo_users
from yitu.identity.models import Role, User
from yitu.identity.service import CurrentUser
from yitu.knowledge.blob_store import LocalBlobStore
from yitu.knowledge.embedding import DeterministicEmbedding
from yitu.knowledge.lifecycle import change_document_status
from yitu.knowledge.mineru_client import MinerUTask
from yitu.knowledge.models import DocumentStatus, KnowledgeChunk, KnowledgeDocument
from yitu.knowledge.retrieval import KnowledgeRetriever
from yitu.knowledge.schemas import KnowledgeReviewRequest
from yitu.knowledge.service import upload_document
from yitu.knowledge.tasks import (
    PollOutcome,
    _poll_mineru_document,
    _submit_mineru_document,
)
from yitu.platform.database import SessionFactory


class FixedBlobStore(LocalBlobStore):
    """为固定旅程提供可签名的本地对象存储替身。"""

    def presign_get(self, key: str, expires_seconds: int = 900) -> str:
        del expires_seconds
        return f"fixed://{key}"


class FixedMinerUGateway:
    """固定返回完成结果的 MinerU 适配器，不访问外部服务。"""

    def __init__(self, archive: bytes) -> None:
        self.archive = archive
        self.task_id = f"smoke-{uuid4()}"

    async def submit(self, source_url: str) -> str:
        del source_url
        return self.task_id

    async def get_task(self, task_id: str) -> MinerUTask:
        return MinerUTask(task_id, "done", "fixed://result.zip", None)

    async def download_result(self, url: str) -> bytes:
        del url
        return self.archive


def _archive(markdown: str) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("result/full.md", markdown.encode("utf-8"))
    return buffer.getvalue()


async def run() -> dict[str, object]:
    """执行上传、解析、审核、发布和检索，并清理本次旅程数据。"""
    document_id: UUID | None = None
    user_id: UUID | None = None
    smoke_root = Path(tempfile.mkdtemp(prefix="yitu-rag-smoke-"))
    store = FixedBlobStore(str(smoke_root))
    try:
        async with SessionFactory() as session:
            users = await seed_demo_users(session)
            admin = next(
                user for user in users if Role(user.role) is Role.SYSTEM_ADMIN
            )
            user_id = admin.id
            document = await upload_document(
                session,
                store,
                filename="fixed-rag-smoke.pdf",
                content_type="application/pdf",
                data=b"%PDF-1.4\n/Type /Page\n%%EOF",
                uploaded_by=admin.id,
                max_bytes=20 * 1024 * 1024,
            )
            document_id = document.id
            # 上传服务已提交原始 PDF，这里单独提交队列状态转换。
            document.status = DocumentStatus.QUEUED
            await session.commit()

        markdown = (
            "<!-- page: 3 -->\n# 派送规则\n\n"
            "| 项目 | 说明 |\n| --- | --- |\n| 派送时效 | 北京至上海 1 天 |"
        )
        gateway = FixedMinerUGateway(_archive(markdown))
        await _submit_mineru_document(document_id, store=store, client=gateway)
        outcome = await _poll_mineru_document(
            document_id,
            store=store,
            client=gateway,
            embedding_provider=DeterministicEmbedding(),
        )
        if outcome is not PollOutcome.COMPLETED:
            raise RuntimeError(f"fixed MinerU journey did not complete: {outcome}")

        async with SessionFactory() as session, session.begin():
            admin_user = await session.get(User, user_id)
            parsed_document = await session.get(KnowledgeDocument, document_id)
            if admin_user is None or parsed_document is None:
                raise RuntimeError("fixed journey document or admin is missing")
            await change_document_status(
                session,
                parsed_document.id,
                CurrentUser(admin_user.id, admin_user.role, admin_user.station_id),
                DocumentStatus.REVIEW_REQUIRED,
                KnowledgeReviewRequest(
                    category="delivery-rules",
                ),
            )
            await change_document_status(
                session,
                parsed_document.id,
                CurrentUser(admin_user.id, admin_user.role, admin_user.station_id),
                DocumentStatus.PUBLISHED,
            )

        async with SessionFactory() as session:
            provider = DeterministicEmbedding()
            evidence = await KnowledgeRetriever(session, provider).search(
                "派送时效",
                category="delivery-rules",
                limit=5,
            )
            chunk = await session.scalar(
                select(KnowledgeChunk).where(
                    KnowledgeChunk.document_id == document_id
                )
            )
            published_document = await session.get(KnowledgeDocument, document_id)
            if published_document is None or chunk is None:
                raise RuntimeError("fixed journey index is missing")
            return {
                "document_id": str(published_document.id),
                "status": DocumentStatus(published_document.status).value,
                "parser": published_document.parser_name,
                "embedding_model": chunk.embedding_model,
                "embedding_dimension": chunk.embedding_dimension,
                "evidence_count": len(evidence),
                "content_type": chunk.content_type,
                "page_start": chunk.page_start,
            }
    finally:
        async with SessionFactory() as session, session.begin():
            if document_id is not None:
                await session.execute(
                    delete(KnowledgeDocument).where(
                        KnowledgeDocument.id == document_id
                    )
                )
        shutil.rmtree(smoke_root, ignore_errors=True)


if __name__ == "__main__":
    print(json.dumps(asyncio.run(run()), ensure_ascii=False, sort_keys=True))
