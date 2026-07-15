from pathlib import PurePosixPath


class HlsObjectNotFound(ValueError):
    """Requested object is not part of a verified HLS rendition."""


def resolve_hls_object_key(*, storage_key: str, metadata: object, object_name: str) -> str:
    """Resolve a safe sibling object and require exact inventory membership."""
    path = PurePosixPath(object_name)
    if path.name != object_name or object_name in {"", ".", ".."}:
        raise HlsObjectNotFound(object_name)
    if not isinstance(metadata, dict):
        raise HlsObjectNotFound(object_name)
    inventory = metadata.get("object_keys")
    if not isinstance(inventory, list) or not all(isinstance(key, str) for key in inventory):
        raise HlsObjectNotFound(object_name)
    object_key = str(PurePosixPath(storage_key).parent / object_name)
    if object_key not in inventory:
        raise HlsObjectNotFound(object_name)
    return object_key
