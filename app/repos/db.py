from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    Session,
    mapped_column,
    relationship,
    sessionmaker,
)

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[UUID]:
    return mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)


def _ts_now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Config(Base):
    __tablename__ = "configs"

    id: Mapped[UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = _ts_now()
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    versions: Mapped[list["ConfigVersion"]] = relationship(
        back_populates="config",
        cascade="all, delete-orphan",
        order_by="ConfigVersion.version",
    )


class ConfigVersion(Base):
    __tablename__ = "config_versions"
    __table_args__ = (UniqueConstraint("config_id", "version", name="uq_config_version"),)

    id: Mapped[UUID] = _uuid_pk()
    config_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("configs.id", ondelete="CASCADE"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    fields: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    provider_options: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = _ts_now()

    config: Mapped[Config] = relationship(back_populates="versions")


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = _ts_now()

    documents: Mapped[list["DatasetDocument"]] = relationship(
        back_populates="dataset",
        cascade="all, delete-orphan",
    )


class DatasetDocument(Base):
    __tablename__ = "dataset_documents"
    __table_args__ = (UniqueConstraint("dataset_id", "doc_key", name="uq_dataset_doc"),)

    id: Mapped[UUID] = _uuid_pk()
    dataset_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False
    )
    doc_key: Mapped[str] = mapped_column(String, nullable=False)
    blob_path: Mapped[str] = mapped_column(String, nullable=False)
    mime_type: Mapped[str] = mapped_column(String, nullable=False)
    ground_truth: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    doc_metadata: Mapped[dict[str, Any] | None] = mapped_column(
        JSONB, nullable=True
    )

    dataset: Mapped[Dataset] = relationship(back_populates="documents")


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[UUID] = _uuid_pk()
    config_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("config_versions.id"), nullable=False
    )
    blob_path: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    extraction: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(10, 4), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = _ts_now()


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[UUID] = _uuid_pk()
    config_version_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("config_versions.id"), nullable=False
    )
    dataset_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("datasets.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String, nullable=False)
    summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = _ts_now()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EvaluationDocument(Base):
    __tablename__ = "evaluation_documents"

    evaluation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("evaluations.id", ondelete="CASCADE"),
        primary_key=True,
    )
    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("dataset_documents.id"),
        primary_key=True,
    )
    extraction: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    field_statuses: Mapped[dict[str, str] | None] = mapped_column(JSONB, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class OCRCache(Base):
    __tablename__ = "ocr_cache"

    id: Mapped[UUID] = _uuid_pk()
    cache_key: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    extraction: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = _ts_now()


_engine = None
_session_factory: sessionmaker[Session] | None = None


def get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True, future=True)
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    return _session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
