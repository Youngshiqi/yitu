from pathlib import Path
from typing import BinaryIO, Protocol

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


def get_blob_store() -> BlobStore:
    settings = get_settings()
    if settings.knowledge_storage_backend != "local":
        raise RuntimeError("S3 BlobStore is not configured in this deployment")
    return LocalBlobStore(settings.knowledge_storage_root)
