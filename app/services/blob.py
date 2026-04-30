from functools import lru_cache
from typing import Optional

from azure.storage.blob import BlobServiceClient, ContentSettings

from app.core.config import get_settings


@lru_cache(maxsize=1)
def _client() -> BlobServiceClient:
    return BlobServiceClient.from_connection_string(get_settings().azure_storage_connection_string)


def ensure_containers() -> None:
    s = get_settings()
    client = _client()
    for container in (s.blob_container_documents, s.blob_container_datasets):
        try:
            client.create_container(container)
        except Exception:
            pass  # already exists


def upload(container: str, blob_name: str, data: bytes, content_type: str = "application/octet-stream") -> str:
    blob = _client().get_blob_client(container=container, blob=blob_name)
    blob.upload_blob(data, overwrite=True, content_settings=ContentSettings(content_type=content_type))
    return f"{container}/{blob_name}"


def download(container: str, blob_name: str) -> bytes:
    blob = _client().get_blob_client(container=container, blob=blob_name)
    return blob.download_blob().readall()


def download_from_path(blob_path: str) -> bytes:
    parts = blob_path.split("/", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid blob_path: {blob_path!r}")
    return download(parts[0], parts[1])


def mime_for_filename(filename: str) -> str:
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    return {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
    }.get(ext, "application/octet-stream")
