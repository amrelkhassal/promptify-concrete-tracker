from typing import Any, Optional
from uuid import UUID

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from app.domain.models import ConfigVersionData, FieldSpec, ProviderName
from app.repos.db import Config, ConfigVersion


def _to_data(cfg: Config, ver: ConfigVersion) -> ConfigVersionData:
    return ConfigVersionData(
        config_id=cfg.id,
        config_name=cfg.name,
        version=ver.version,
        prompt=ver.prompt,
        fields=[FieldSpec(**f) for f in ver.fields],
        provider=ProviderName(ver.provider),
        provider_options=ver.provider_options or {},
        notes=ver.notes,
        created_by=ver.created_by,
        created_at=ver.created_at,
    )


def list_configs(session: Session) -> list[dict[str, Any]]:
    """Return list of {config, latest_version} for the configs index page."""
    latest_subq = (
        select(
            ConfigVersion.config_id,
            func.max(ConfigVersion.version).label("max_version"),
        )
        .group_by(ConfigVersion.config_id)
        .subquery()
    )
    stmt = (
        select(Config, ConfigVersion)
        .join(latest_subq, latest_subq.c.config_id == Config.id)
        .join(
            ConfigVersion,
            (ConfigVersion.config_id == Config.id)
            & (ConfigVersion.version == latest_subq.c.max_version),
        )
        .order_by(Config.name)
    )
    out: list[dict[str, Any]] = []
    for cfg, ver in session.execute(stmt).all():
        out.append({"config": cfg, "latest_version": ver, "data": _to_data(cfg, ver)})
    return out


def get_config_by_name(session: Session, name: str) -> Optional[Config]:
    return session.execute(select(Config).where(Config.name == name)).scalar_one_or_none()


def get_version(session: Session, config_version_id: UUID) -> Optional[ConfigVersionData]:
    row = session.execute(
        select(Config, ConfigVersion)
        .join(ConfigVersion, ConfigVersion.config_id == Config.id)
        .where(ConfigVersion.id == config_version_id)
    ).one_or_none()
    if not row:
        return None
    cfg, ver = row
    return _to_data(cfg, ver)


def get_latest_version(session: Session, config_name: str) -> Optional[ConfigVersionData]:
    cfg = get_config_by_name(session, config_name)
    if not cfg:
        return None
    ver = session.execute(
        select(ConfigVersion)
        .where(ConfigVersion.config_id == cfg.id)
        .order_by(desc(ConfigVersion.version))
        .limit(1)
    ).scalar_one_or_none()
    if not ver:
        return None
    return _to_data(cfg, ver)


def list_versions(session: Session, config_id: UUID) -> list[ConfigVersionData]:
    rows = session.execute(
        select(Config, ConfigVersion)
        .join(ConfigVersion, ConfigVersion.config_id == Config.id)
        .where(ConfigVersion.config_id == config_id)
        .order_by(desc(ConfigVersion.version))
    ).all()
    return [_to_data(cfg, ver) for cfg, ver in rows]


def create_config(
    session: Session,
    *,
    name: str,
    description: Optional[str],
    prompt: str,
    fields: list[FieldSpec],
    provider: ProviderName,
    provider_options: dict[str, Any],
    notes: Optional[str],
    created_by: str,
) -> ConfigVersionData:
    """Create a new config + its v1 version atomically."""
    cfg = Config(name=name, description=description, created_by=created_by)
    session.add(cfg)
    session.flush()
    ver = ConfigVersion(
        config_id=cfg.id,
        version=1,
        prompt=prompt,
        fields=[f.model_dump(mode="json") for f in fields],
        provider=provider.value,
        provider_options=provider_options,
        notes=notes,
        created_by=created_by,
    )
    session.add(ver)
    session.flush()
    return _to_data(cfg, ver)


def add_version(
    session: Session,
    *,
    config_id: UUID,
    prompt: str,
    fields: list[FieldSpec],
    provider: ProviderName,
    provider_options: dict[str, Any],
    notes: Optional[str],
    created_by: str,
) -> ConfigVersionData:
    cfg = session.get(Config, config_id)
    if cfg is None:
        raise ValueError(f"Config {config_id} not found")
    next_version = (
        session.execute(
            select(func.coalesce(func.max(ConfigVersion.version), 0))
            .where(ConfigVersion.config_id == config_id)
        ).scalar_one()
    ) + 1
    ver = ConfigVersion(
        config_id=config_id,
        version=next_version,
        prompt=prompt,
        fields=[f.model_dump(mode="json") for f in fields],
        provider=provider.value,
        provider_options=provider_options,
        notes=notes,
        created_by=created_by,
    )
    session.add(ver)
    session.flush()
    return _to_data(cfg, ver)
