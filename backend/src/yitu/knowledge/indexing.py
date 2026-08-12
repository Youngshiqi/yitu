from datetime import UTC, datetime
from uuid import UUID, uuid5

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from yitu.knowledge.chunking import ChunkingPolicy
from yitu.knowledge.embedding import (
    QWEN_EMBEDDING_DIMENSION,
    EmbeddingProvider,
    get_embedding_provider,
)
from yitu.knowledge.models import KnowledgeChunk, KnowledgeDocument
from yitu.platform.errors import AppError


async def build_index_version(
    session: AsyncSession,
    document_id: UUID,
    *,
    provider: EmbeddingProvider | None = None,
    policy: ChunkingPolicy | None = None,
) -> int:
    """为已解析文档创建新索引版本，并持久化生成向量的模型元数据。"""
    document = await session.get(KnowledgeDocument, document_id)
    if document is None or not document.parsed_text:
        raise AppError(
            "KNOWLEDGE_DOCUMENT_NOT_PARSED",
            "document has no parsed content",
            409,
        )
    latest_version = await session.scalar(
        select(KnowledgeChunk.index_version)
        .where(KnowledgeChunk.document_id == document_id)
        .order_by(KnowledgeChunk.index_version.desc())
        .limit(1)
    )
    version = (latest_version or 0) + 1
    chunking_policy = policy or ChunkingPolicy()
    chunks = chunking_policy.chunk(document.parsed_text)
    selected_provider = provider or get_embedding_provider()
    vectors = selected_provider.embed([chunk.content for chunk in chunks])
    dimension = selected_provider.dimension
    if dimension != QWEN_EMBEDDING_DIMENSION:
        raise AppError(
            "KNOWLEDGE_EMBEDDING_DIMENSION_MISMATCH",
            "embedding dimension does not match the knowledge index",
            409,
        )
    await session.execute(
        delete(KnowledgeChunk).where(
            KnowledgeChunk.document_id == document_id,
            KnowledgeChunk.index_version == version,
        )
    )
    now = datetime.now(UTC)
    session.add_all(
        [
            KnowledgeChunk(
                # 使用文档、版本和块内容生成稳定 UUID，重建同一版本不会产生重复身份。
                id=uuid5(
                    document.id,
                    f"{version}:{chunk.index}:{chunk.content}",
                ),
                document_id=document_id,
                index_version=version,
                chunk_index=chunk.index,
                content=chunk.content,
                embedding=vectors[chunk.index],
                embedding_model=selected_provider.model,
                embedding_dimension=dimension,
                title=chunk.title,
                section_path=list(chunk.section_path),
                content_type=chunk.content_type,
                chunking_version=chunking_policy.version,
                indexed_at=now,
                page_start=chunk.page_start,
                page_end=chunk.page_end,
                created_at=now,
            )
            for chunk in chunks
        ]
    )
    await session.flush()
    return version
