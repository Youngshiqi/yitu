from pathlib import Path
from typing import Any

import pytest

from yitu.knowledge.blob_store import LocalBlobStore, S3BlobStore


class FakeS3Client:
    def __init__(self) -> None:
        self.put_kwargs: dict[str, Any] = {}
        self.presign_kwargs: dict[str, Any] = {}

    def put_object(self, **kwargs: Any) -> None:
        self.put_kwargs = kwargs

    def generate_presigned_url(self, operation: str, **kwargs: Any) -> str:
        self.presign_kwargs = {"operation": operation, **kwargs}
        return "https://signed.example/object"


def test_local_store_preserves_bytes_and_rejects_signing(tmp_path: Path) -> None:
    store = LocalBlobStore(str(tmp_path))
    store.put("artifacts/result.md", b"markdown", "text/markdown")

    with store.open("artifacts/result.md") as handle:
        assert handle.read() == b"markdown"
    with pytest.raises(NotImplementedError):
        store.presign_get("artifacts/result.md")


def test_s3_store_forwards_mime_and_presign_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeS3Client()
    monkeypatch.setattr("yitu.knowledge.blob_store.boto3.client", lambda *args, **kwargs: client)
    store = S3BlobStore("https://cos.example", "bucket", "key", "secret", "region")

    store.put("documents/a.pdf", b"pdf", "application/pdf")
    url = store.presign_get("documents/a.pdf", 900)

    assert client.put_kwargs["ContentType"] == "application/pdf"
    assert client.put_kwargs["ServerSideEncryption"] == "AES256"
    assert client.presign_kwargs["operation"] == "get_object"
    assert client.presign_kwargs["ExpiresIn"] == 900
    assert url == "https://signed.example/object"


def test_s3_store_rejects_unsafe_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FakeS3Client()
    monkeypatch.setattr("yitu.knowledge.blob_store.boto3.client", lambda *args, **kwargs: client)
    store = S3BlobStore("https://cos.example", "bucket", "key", "secret", "region")

    with pytest.raises(ValueError):
        store.presign_get("documents/a.pdf", 10)
