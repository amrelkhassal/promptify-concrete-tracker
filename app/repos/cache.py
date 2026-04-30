import hashlib
import json
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.domain.models import FieldSpec, ProviderName
from app.repos.db import OCRCache


def _canonical_fields(fields: list[FieldSpec]) -> str:
    payload = [
        {
            "name": f.name,
            "label": f.label,
            "description": f.description,
            "example": f.example,
            "type": f.type.value,
        }
        for f in fields
    ]
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def compute_cache_key(
    *,
    provider: ProviderName,
    prompt: str,
    fields: list[FieldSpec],
    file_bytes: bytes,
) -> str:
    h = hashlib.sha256()
    h.update(provider.value.encode())
    h.update(b"|")
    h.update(hashlib.sha256(prompt.encode()).digest())
    h.update(b"|")
    h.update(hashlib.sha256(_canonical_fields(fields).encode()).digest())
    h.update(b"|")
    h.update(hashlib.sha256(file_bytes).digest())
    return h.hexdigest()


def get(session: Session, cache_key: str) -> Optional[OCRCache]:
    return session.execute(
        select(OCRCache).where(OCRCache.cache_key == cache_key)
    ).scalar_one_or_none()


def put(
    session: Session,
    *,
    cache_key: str,
    provider: ProviderName,
    extraction: dict[str, Any],
    ocr_text: Optional[str],
    raw_response: Optional[dict[str, Any]] = None,
) -> None:
    stmt = pg_insert(OCRCache).values(
        cache_key=cache_key,
        provider=provider.value,
        extraction=extraction,
        ocr_text=ocr_text,
        raw_response=raw_response,
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["cache_key"],
        set_={
            "extraction": stmt.excluded.extraction,
            "ocr_text": stmt.excluded.ocr_text,
            "raw_response": stmt.excluded.raw_response,
        },
    )
    session.execute(stmt)
    session.flush()
