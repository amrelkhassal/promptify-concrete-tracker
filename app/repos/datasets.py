from typing import Any, Optional
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.repos.db import Dataset, DatasetDocument


def create_dataset(
    session: Session,
    *,
    name: str,
    description: Optional[str],
    created_by: str,
) -> Dataset:
    ds = Dataset(name=name, description=description, created_by=created_by)
    session.add(ds)
    session.flush()
    return ds


def get_dataset_by_name(session: Session, name: str) -> Optional[Dataset]:
    return session.execute(select(Dataset).where(Dataset.name == name)).scalar_one_or_none()


def list_datasets(session: Session) -> list[dict[str, Any]]:
    count_subq = (
        select(DatasetDocument.dataset_id, func.count().label("doc_count"))
        .group_by(DatasetDocument.dataset_id)
        .subquery()
    )
    stmt = (
        select(Dataset, count_subq.c.doc_count)
        .outerjoin(count_subq, count_subq.c.dataset_id == Dataset.id)
        .order_by(Dataset.name)
    )
    return [
        {"dataset": ds, "doc_count": doc_count or 0}
        for ds, doc_count in session.execute(stmt).all()
    ]


def add_document(
    session: Session,
    *,
    dataset_id: UUID,
    doc_key: str,
    blob_path: str,
    mime_type: str,
    ground_truth: dict[str, Any],
    metadata: Optional[dict[str, Any]] = None,
) -> DatasetDocument:
    stmt = (
        pg_insert(DatasetDocument)
        .values(
            dataset_id=dataset_id,
            doc_key=doc_key,
            blob_path=blob_path,
            mime_type=mime_type,
            ground_truth=ground_truth,
            metadata=metadata,
        )
        .on_conflict_do_update(
            constraint="uq_dataset_doc",
            set_={
                "blob_path": blob_path,
                "mime_type": mime_type,
                "ground_truth": ground_truth,
                "metadata": metadata,
            },
        )
        .returning(DatasetDocument)
    )
    return session.execute(stmt).scalar_one()


def get_documents(session: Session, dataset_id: UUID) -> list[DatasetDocument]:
    return list(
        session.execute(
            select(DatasetDocument).where(DatasetDocument.dataset_id == dataset_id)
        )
        .scalars()
        .all()
    )
