from typing import cast

from pgvector.sqlalchemy import Vector
from sqlalchemy import Table, text

from yitu.knowledge.embedding import QWEN_EMBEDDING_DIMENSION
from yitu.knowledge.models import KnowledgeChunk
from yitu.platform.database import SessionFactory


def test_knowledge_chunk_model_uses_production_vector_schema() -> None:
    """模型元数据必须固定向量维度和两类生产检索索引。"""
    table = cast(Table, KnowledgeChunk.__table__)

    assert isinstance(table.c.embedding.type, Vector)
    assert table.c.embedding.type.dim == QWEN_EMBEDDING_DIMENSION
    assert table.c.embedding_model.nullable is False
    assert table.c.embedding_dimension.nullable is False

    vector_index = next(
        index
        for index in table.indexes
        if index.name == "ix_knowledge_chunks_embedding_hnsw"
    )
    assert vector_index.dialect_options["postgresql"]["using"] == "hnsw"
    assert vector_index.dialect_options["postgresql"]["ops"] == {
        "embedding": "vector_cosine_ops"
    }
    content_index = next(
        index
        for index in table.indexes
        if index.name == "ix_knowledge_chunks_content_fts"
    )
    assert content_index.dialect_options["postgresql"]["using"] == "gin"


async def test_database_has_knowledge_vector_indexes() -> None:
    """真实 PostgreSQL 必须完成扩展、列类型、约束和索引迁移。"""
    async with SessionFactory() as session:
        extension = await session.scalar(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        )
        embedding_type = await session.scalar(
            text(
                "SELECT format_type(a.atttypid, a.atttypmod) "
                "FROM pg_attribute a "
                "JOIN pg_class c ON c.oid = a.attrelid "
                "WHERE c.relname = 'knowledge_chunks' "
                "AND a.attname = 'embedding' AND NOT a.attisdropped"
            )
        )
        constraints = set(
            (
                await session.execute(
                    text(
                        "SELECT conname FROM pg_constraint "
                        "WHERE conrelid = 'knowledge_chunks'::regclass"
                    )
                )
            ).scalars()
        )
        index_rows = (
            await session.execute(
                text(
                    "SELECT indexname, indexdef FROM pg_indexes "
                    "WHERE schemaname = current_schema() "
                    "AND tablename = 'knowledge_chunks'"
                )
            )
        ).tuples()
        index_definitions: dict[str, str] = {
            str(name): str(definition) for name, definition in index_rows
        }

    assert extension is not None
    assert embedding_type == f"vector({QWEN_EMBEDDING_DIMENSION})"
    assert "ck_knowledge_chunks_embedding_dimension" in constraints
    assert "ck_knowledge_chunks_embedding_model" in constraints
    assert "USING hnsw" in index_definitions["ix_knowledge_chunks_embedding_hnsw"]
    assert "vector_cosine_ops" in index_definitions[
        "ix_knowledge_chunks_embedding_hnsw"
    ]
    assert "USING gin" in index_definitions["ix_knowledge_chunks_content_fts"]
    assert "to_tsvector('simple'::regconfig" in index_definitions[
        "ix_knowledge_chunks_content_fts"
    ]
