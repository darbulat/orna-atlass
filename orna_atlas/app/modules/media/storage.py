from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from collections.abc import Iterator
from pathlib import Path

from orna_atlas.app.integrations.s3 import (
    ObjectStorageClient,
    StorageReference,
    get_object_storage_client,
    parse_storage_reference,
)


def storage_reference(storage_key: str, *, client: ObjectStorageClient | None = None) -> StorageReference:
    storage_client = client or get_object_storage_client()
    return parse_storage_reference(storage_key, default_bucket=storage_client.config.private_bucket)


def storage_key_path(storage_key: str, *, client: ObjectStorageClient | None = None) -> Path | None:
    """Return a readable local path when the asset is already on disk."""
    reference = storage_reference(storage_key, client=client)
    if reference.kind != "local" or reference.path is None:
        return None
    if reference.path.exists() and reference.path.is_file():
        return reference.path
    return None


def is_s3_storage_key(storage_key: str, *, client: ObjectStorageClient | None = None) -> bool:
    return storage_reference(storage_key, client=client).kind == "s3"


@contextmanager
def materialize_storage(
    storage_key: str,
    *,
    client: ObjectStorageClient | None = None,
    suffix: str | None = None,
) -> Iterator[Path | None]:
    """Yield a local file path for reading audio bytes from disk or S3."""
    storage_client = client or get_object_storage_client()
    reference = storage_reference(storage_key, client=storage_client)

    if reference.kind == "local":
        if reference.path is not None and reference.path.exists() and reference.path.is_file():
            yield reference.path
        else:
            yield None
        return

    if not storage_client.is_configured():
        yield None
        return

    if reference.key is None:
        yield None
        return

    inferred_suffix = suffix or Path(reference.key).suffix or ".bin"
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=inferred_suffix)
    temp_file.close()
    temp_path = Path(temp_file.name)
    try:
        storage_client.download_file(reference.key, temp_path, bucket=reference.bucket)
        yield temp_path
    finally:
        if temp_path.exists():
            os.unlink(temp_path)
