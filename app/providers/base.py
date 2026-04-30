from abc import ABC, abstractmethod
from typing import Any

from app.domain.models import Extraction, FieldSpec, ProviderName


class ProviderError(Exception):
    pass


class OCRProvider(ABC):
    name: ProviderName

    @abstractmethod
    def run(
        self,
        file_bytes: bytes,
        mime_type: str,
        prompt: str,
        fields: list[FieldSpec],
        options: dict[str, Any],
    ) -> Extraction: ...


def detect_media_type(file_bytes: bytes, filename: str = "") -> str:
    if file_bytes[:4] == b"%PDF":
        return "application/pdf"
    if file_bytes[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if file_bytes[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if file_bytes[:4] == b"RIFF" and file_bytes[8:12] == b"WEBP":
        return "image/webp"
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    ext_map = {
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "webp": "image/webp",
    }
    if ext in ext_map:
        return ext_map[ext]
    raise ProviderError("Cannot detect file type. Supported: PNG, JPEG, WEBP, PDF.")
