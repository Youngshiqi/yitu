from io import BytesIO
from pathlib import Path
from typing import BinaryIO, Protocol

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]

from yitu.platform.config import get_settings


class BlobStore(Protocol):
    def put(self, key: str, data: bytes, content_type: str) -> None: ...
    def open(self, key: str) -> BinaryIO: ...
    def delete(self, key: str) -> None: ...
    def presign_get(self, key: str, expires_seconds: int = 900) -> str: ...


class LocalBlobStore:
    def __init__(self, root: str) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("invalid object key")
        return path

    def put(self, key: str, data: bytes, content_type: str) -> None:
        """本地存储保留统一 MIME 参数，文件内容保持原始字节。"""
        del content_type
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def open(self, key: str) -> BinaryIO:
        return self._path(key).open("rb")

    def delete(self, key: str) -> None:
        path = self._path(key)
        if path.exists():
            path.unlink()

    def presign_get(self, key: str, expires_seconds: int = 900) -> str:
        """本地存储没有可供外部 MinerU 访问的签名 URL。"""
        del key, expires_seconds
        raise NotImplementedError("local BlobStore does not support presigned URLs")


class S3BlobStore:
    def __init__(self, endpoint: str, bucket: str, access_key: str, secret_key: str, region: str) -> None:
        self.bucket = bucket
        self.client = boto3.client(
            "s3", endpoint_url=endpoint, aws_access_key_id=access_key,
            aws_secret_access_key=secret_key, region_name=region,
            # 腾讯 COS 仅接受 bucket 位于主机名中的 virtual-hosted-style 请求。
            config=Config(s3={"addressing_style": "virtual"}),
        )

    def put(self, key: str, data: bytes, content_type: str) -> None:
        """写入私有 COS 对象，并使用 COS 托管密钥进行服务端加密。"""
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type, ServerSideEncryption="AES256")

    def open(self, key: str) -> BinaryIO:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return BytesIO(response["Body"].read())

    def delete(self, key: str) -> None:
        self.client.delete_object(Bucket=self.bucket, Key=key)

    def presign_get(self, key: str, expires_seconds: int = 900) -> str:
        """生成仅供解析服务短时读取私有对象的签名 URL。"""
        if not 60 <= expires_seconds <= 3600:
            raise ValueError("presigned URL expiry must be between 60 and 3600 seconds")
        return str(self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": key},
            ExpiresIn=expires_seconds,
        ))


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
