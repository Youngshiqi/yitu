from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Protocol

import boto3  # type: ignore[import-untyped]

from yitu.platform.config import get_settings


class BlobStore(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def open(self, key: str) -> BinaryIO: ...
    def delete(self, key: str) -> None: ...


class LocalBlobStore:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("invalid object key")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def open(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()


class S3BlobStore:
    def __init__(self, endpoint: str, bucket: str, access_key: str, secret_key: str, region: str) -> None:
        self.bucket = bucket
        self.client = boto3.client(
            "s3", endpoint_url=endpoint, aws_access_key_id=access_key,
            aws_secret_access_key=secret_key, region_name=region,
        )

    def put(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType="application/pdf", ServerSideEncryption="AES256")

    def open(self, key: str) -> BinaryIO:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return BytesIO(response["Body"].read())

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)


def get_blob_store() -> BlobStore:
    settings = get_settings()
    if settings.knowledge_storage_backend == "s3":
        if not all((settings.knowledge_s3_endpoint, settings.knowledge_s3_access_key, settings.knowledge_s3_secret_key)):
            raise RuntimeError("S3 BlobStore credentials are not configured")
        endpoint = settings.knowledge_s3_endpoint
        access_key = settings.knowledge_s3_access_key
        secret_key = settings.knowledge_s3_secret_key
        assert endpoint is not None and access_key is not None and secret_key is not None
        return S3BlobStore(endpoint, settings.knowledge_s3_bucket, access_key, secret_key, settings.knowledge_s3_region)
    return LocalBlobStore(settings.knowledge_storage_root)
