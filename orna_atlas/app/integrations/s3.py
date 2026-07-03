from dataclasses import dataclass


@dataclass(frozen=True)
class ObjectStorageConfig:
    endpoint_url: str | None = None
    bucket_name: str = "orna-atlas-local"


class ObjectStorageClient:
    def __init__(self, config: ObjectStorageConfig | None = None) -> None:
        self.config = config or ObjectStorageConfig()

    def public_url(self, key: str) -> str:
        return f"s3://{self.config.bucket_name}/{key}"
