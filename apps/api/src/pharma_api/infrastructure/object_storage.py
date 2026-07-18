from __future__ import annotations

import shutil
from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import BinaryIO, Protocol

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from pharma_api.core.config import Settings, get_settings


class ObjectAlreadyExistsError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StoredObject:
    bucket: str
    key: str
    size_bytes: int
    content_type: str


class ObjectStorage(Protocol):
    bucket: str

    def put_file(
        self, path: Path, *, key: str, content_type: str, metadata: dict[str, str]
    ) -> StoredObject: ...

    def iter_object(self, key: str, *, chunk_size: int = 1_048_576) -> Iterator[bytes]: ...

    def delete_object(self, key: str) -> None: ...

    def presigned_download(self, key: str, *, expires_seconds: int = 60) -> str | None: ...


def validate_object_key(key: str) -> str:
    normalized = PurePosixPath(key)
    if not key or normalized.is_absolute() or ".." in normalized.parts or "\\" in key:
        raise ValueError("Unsafe object key")
    return normalized.as_posix()


class FilesystemObjectStorage:
    def __init__(self, root: Path, bucket: str) -> None:
        self.root = root.resolve()
        self.bucket = bucket

    def _path(self, key: str) -> Path:
        safe_key = validate_object_key(key)
        target = (self.root / self.bucket / Path(*PurePosixPath(safe_key).parts)).resolve()
        if self.root not in target.parents:
            raise ValueError("Object key escapes storage root")
        return target

    def put_file(
        self, path: Path, *, key: str, content_type: str, metadata: dict[str, str]
    ) -> StoredObject:
        del metadata
        destination = self._path(key)
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            with path.open("rb") as source, destination.open("xb") as output:
                shutil.copyfileobj(source, output, length=1_048_576)
        except FileExistsError as exc:
            raise ObjectAlreadyExistsError(key) from exc
        return StoredObject(
            self.bucket, validate_object_key(key), path.stat().st_size, content_type
        )

    def iter_object(self, key: str, *, chunk_size: int = 1_048_576) -> Iterator[bytes]:
        with self._path(key).open("rb") as source:
            while chunk := source.read(chunk_size):
                yield chunk

    def delete_object(self, key: str) -> None:
        self._path(key).unlink(missing_ok=True)

    def presigned_download(self, key: str, *, expires_seconds: int = 60) -> str | None:
        del key, expires_seconds
        return None


class S3ObjectStorage:
    def __init__(self, settings: Settings) -> None:
        self.bucket = settings.s3_bucket
        self._server_side_encryption = settings.s3_server_side_encryption
        secret = (
            settings.s3_secret_access_key.get_secret_value()
            if settings.s3_secret_access_key
            else None
        )
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            region_name=settings.s3_region,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=secret,
            config=Config(
                signature_version="s3v4", retries={"max_attempts": 4, "mode": "standard"}
            ),
        )

    def put_file(
        self, path: Path, *, key: str, content_type: str, metadata: dict[str, str]
    ) -> StoredObject:
        safe_key = validate_object_key(key)
        try:
            self._client.head_object(Bucket=self.bucket, Key=safe_key)
        except ClientError as exc:
            status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
            if status not in {403, 404}:
                raise
        else:
            raise ObjectAlreadyExistsError(safe_key)
        extra_args = {
            "ContentType": content_type,
            "Metadata": {str(key): str(value)[:1_024] for key, value in metadata.items()},
        }
        if self._server_side_encryption is not None:
            extra_args["ServerSideEncryption"] = self._server_side_encryption
        with path.open("rb") as source:
            self._client.upload_fileobj(
                source,
                self.bucket,
                safe_key,
                ExtraArgs=extra_args,
            )
        return StoredObject(self.bucket, safe_key, path.stat().st_size, content_type)

    def iter_object(self, key: str, *, chunk_size: int = 1_048_576) -> Iterator[bytes]:
        response = self._client.get_object(Bucket=self.bucket, Key=validate_object_key(key))
        body: BinaryIO = response["Body"]
        try:
            while chunk := body.read(chunk_size):
                yield chunk
        finally:
            body.close()

    def delete_object(self, key: str) -> None:
        self._client.delete_object(Bucket=self.bucket, Key=validate_object_key(key))

    def presigned_download(self, key: str, *, expires_seconds: int = 60) -> str:
        return str(
            self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": validate_object_key(key)},
                ExpiresIn=max(1, min(expires_seconds, 300)),
            )
        )


@lru_cache(maxsize=1)
def get_object_storage() -> ObjectStorage:
    settings = get_settings()
    if settings.object_storage_backend == "s3":
        return S3ObjectStorage(settings)
    return FilesystemObjectStorage(settings.object_storage_root, settings.s3_bucket)


def close_object_storage() -> None:
    get_object_storage.cache_clear()
