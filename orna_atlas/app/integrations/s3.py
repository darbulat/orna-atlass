from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import BinaryIO, Literal

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

from orna_atlas.app.core.config import Settings, get_settings

S3_URI_PREFIX = "s3://"


@dataclass(frozen=True)
class ObjectStorageConfig:
    endpoint_url: str | None = None
    region: str = "us-east-1"
    private_bucket: str = "orna-audio-private"
    public_bucket: str = "orna-media-public"
    access_key_id: str | None = None
    secret_access_key: str | None = None
    presign_expires_seconds: int = 900

    @classmethod
    def from_settings(cls, settings: Settings) -> ObjectStorageConfig:
        return cls(
            endpoint_url=settings.s3_endpoint_url,
            region=settings.s3_region,
            private_bucket=settings.s3_private_bucket,
            public_bucket=settings.s3_public_bucket,
            access_key_id=settings.s3_access_key_id,
            secret_access_key=settings.s3_secret_access_key,
            presign_expires_seconds=settings.s3_presign_expires_seconds,
        )

    def is_configured(self) -> bool:
        return bool(self.endpoint_url or (self.access_key_id and self.secret_access_key))


@dataclass(frozen=True)
class StorageReference:
    kind: Literal["local", "s3"]
    path: Path | None = None
    bucket: str | None = None
    key: str | None = None


def parse_storage_reference(storage_key: str, *, default_bucket: str) -> StorageReference:
    """Resolve a storage key to a local path or S3 object reference."""
    if storage_key.startswith("file://"):
        return StorageReference(kind="local", path=Path(storage_key[7:]))
    if storage_key.startswith(S3_URI_PREFIX):
        without_scheme = storage_key[len(S3_URI_PREFIX) :]
        bucket, separator, key = without_scheme.partition("/")
        if not separator or not key:
            raise ValueError(f"Invalid S3 storage key: {storage_key}")
        return StorageReference(kind="s3", bucket=bucket, key=key)

    candidate = Path(storage_key)
    if candidate.is_absolute():
        return StorageReference(kind="local", path=candidate)
    return StorageReference(kind="s3", bucket=default_bucket, key=storage_key)


class ObjectStorageClient:
    """S3-compatible object storage wrapper for private audio assets."""

    def __init__(self, config: ObjectStorageConfig | None = None) -> None:
        self.config = config or ObjectStorageConfig.from_settings(get_settings())
        self._client: BaseClient | None = None

    def is_configured(self) -> bool:
        return self.config.is_configured()

    def public_url(self, key: str, *, bucket: str | None = None) -> str:
        bucket_name = bucket or self.config.private_bucket
        return f"{S3_URI_PREFIX}{bucket_name}/{key}"

    def object_exists(self, key: str, *, bucket: str | None = None) -> bool:
        bucket_name = bucket or self.config.private_bucket
        try:
            self._get_client().head_object(Bucket=bucket_name, Key=key)
            return True
        except ClientError as exc:
            error_code = exc.response.get("Error", {}).get("Code")
            if error_code in {"404", "NoSuchKey", "NotFound"}:
                return False
            raise

    def download_file(self, key: str, destination: Path | str, *, bucket: str | None = None) -> None:
        bucket_name = bucket or self.config.private_bucket
        destination_path = Path(destination)
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        self._get_client().download_file(bucket_name, key, str(destination_path))

    def upload_file(
        self,
        source: Path | str,
        key: str,
        *,
        bucket: str | None = None,
        content_type: str | None = None,
    ) -> None:
        bucket_name = bucket or self.config.private_bucket
        extra_args = {"ContentType": content_type} if content_type else None
        self._get_client().upload_file(
            str(source),
            bucket_name,
            key,
            ExtraArgs=extra_args,
        )

    def put_bytes(
        self,
        key: str,
        body: bytes,
        *,
        bucket: str | None = None,
        content_type: str | None = None,
    ) -> None:
        bucket_name = bucket or self.config.private_bucket
        extra_args = {"ContentType": content_type} if content_type else None
        self._get_client().put_object(Bucket=bucket_name, Key=key, Body=body, **(extra_args or {}))

    def copy_object(
        self,
        source_key: str,
        destination_key: str,
        *,
        source_bucket: str | None = None,
        destination_bucket: str | None = None,
        content_type: str | None = None,
    ) -> None:
        source_bucket_name = source_bucket or self.config.private_bucket
        destination_bucket_name = destination_bucket or self.config.private_bucket
        copy_source = {"Bucket": source_bucket_name, "Key": source_key}
        extra_args = {"MetadataDirective": "REPLACE"}
        if content_type:
            extra_args["ContentType"] = content_type
        self._get_client().copy_object(
            Bucket=destination_bucket_name,
            Key=destination_key,
            CopySource=copy_source,
            **extra_args,
        )

    def generate_presigned_get_url(
        self,
        key: str,
        *,
        bucket: str | None = None,
        expires_in: int | None = None,
    ) -> str:
        bucket_name = bucket or self.config.private_bucket
        expiry = expires_in if expires_in is not None else self.config.presign_expires_seconds
        return self._get_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket_name, "Key": key},
            ExpiresIn=expiry,
        )

    def get_object_stream(self, key: str, *, bucket: str | None = None) -> BinaryIO:
        bucket_name = bucket or self.config.private_bucket
        response = self._get_client().get_object(Bucket=bucket_name, Key=key)
        body = response["Body"]
        if not hasattr(body, "read"):
            raise TypeError("S3 object body is not readable")
        return body

    def _get_client(self) -> BaseClient:
        if self._client is None:
            if not self.is_configured():
                raise RuntimeError("Object storage is not configured")
            session = boto3.session.Session(
                aws_access_key_id=self.config.access_key_id,
                aws_secret_access_key=self.config.secret_access_key,
                region_name=self.config.region,
            )
            self._client = session.client(
                "s3",
                endpoint_url=self.config.endpoint_url,
                config=Config(signature_version="s3v4"),
            )
        return self._client


@lru_cache
def get_object_storage_client() -> ObjectStorageClient:
    return ObjectStorageClient()
