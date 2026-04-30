from typing import Any, Optional
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.repos.db import Run


def record_run(
    session: Session,
    *,
    config_version_id: UUID,
    blob_path: str,
    filename: str,
    ocr_text: Optional[str],
    extraction: Optional[dict[str, Any]],
    latency_ms: Optional[int],
    error: Optional[str],
    created_by: str,
) -> Run:
    run = Run(
        config_version_id=config_version_id,
        blob_path=blob_path,
        filename=filename,
        ocr_text=ocr_text,
        extraction=extraction,
        latency_ms=latency_ms,
        error=error,
        created_by=created_by,
    )
    session.add(run)
    session.flush()
    return run


def recent_runs(session: Session, limit: int = 25) -> list[Run]:
    return list(
        session.execute(
            select(Run).order_by(desc(Run.created_at)).limit(limit)
        ).scalars().all()
    )
