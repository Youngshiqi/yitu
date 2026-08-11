from typing import cast

from sqlalchemy import DateTime, Table

from yitu.knowledge.models import KnowledgeDocument
from yitu.knowledge.schemas import KnowledgeDocumentView


def test_document_model_tracks_mineru_workflow() -> None:
    table = cast(Table, KnowledgeDocument.__table__)
    expected_columns = {
        "mineru_task_id",
        "source_artifact_key",
        "markdown_artifact_key",
        "result_archive_key",
        "parse_started_at",
        "parse_finished_at",
    }

    assert expected_columns <= set(table.c.keys())
    assert all(table.c[name].nullable for name in expected_columns)
    assert isinstance(table.c.parse_started_at.type, DateTime)
    assert table.c.parse_started_at.type.timezone is True
    assert isinstance(table.c.parse_finished_at.type, DateTime)
    assert table.c.parse_finished_at.type.timezone is True

    mineru_indexes = [
        index
        for index in table.indexes
        if index.name == "ix_knowledge_documents_mineru_task_id"
    ]
    assert len(mineru_indexes) == 1
    assert mineru_indexes[0].unique is True
    assert [column.name for column in mineru_indexes[0].columns] == ["mineru_task_id"]


def test_document_view_exposes_mineru_recovery_fields() -> None:
    expected_fields = {
        "mineru_task_id",
        "source_artifact_key",
        "markdown_artifact_key",
        "result_archive_key",
        "parse_started_at",
        "parse_finished_at",
    }

    assert expected_fields <= set(KnowledgeDocumentView.model_fields)
