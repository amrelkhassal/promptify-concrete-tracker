from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.domain.models import Extraction, FieldSpec, ProviderName
from app.providers.base import detect_media_type
from app.providers.registry import get_provider
from app.repos import cache as cache_repo


@dataclass
class RunRequest:
    file_bytes: bytes
    filename: str
    prompt: str
    fields: list[FieldSpec]
    provider: ProviderName
    provider_options: dict[str, Any]
    skip_cache_lookup: bool = False


def run_single(session: Session, req: RunRequest) -> Extraction:
    """
    Cache-aware single-image OCR run.

    1. Compute cache_key.
    2. Try cache (unless skip_cache_lookup).
    3. Miss → call provider → store in cache.
    """
    mime_type = detect_media_type(req.file_bytes, req.filename)

    cache_key = cache_repo.compute_cache_key(
        provider=req.provider,
        prompt=req.prompt,
        fields=req.fields,
        file_bytes=req.file_bytes,
    )

    if not req.skip_cache_lookup:
        hit = cache_repo.get(session, cache_key)
        if hit is not None:
            return Extraction(
                fields=hit.extraction or {},
                raw_text=hit.ocr_text,
                raw_response=hit.raw_response or {},
                latency_ms=0,
                cache_hit=True,
            )

    provider = get_provider(req.provider)
    extraction = provider.run(
        file_bytes=req.file_bytes,
        mime_type=mime_type,
        prompt=req.prompt,
        fields=req.fields,
        options=req.provider_options,
    )

    cache_repo.put(
        session,
        cache_key=cache_key,
        provider=req.provider,
        extraction=extraction.fields,
        ocr_text=extraction.raw_text,
        raw_response=extraction.raw_response,
    )

    return extraction
