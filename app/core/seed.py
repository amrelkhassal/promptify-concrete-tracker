import logging

from app.core.auth import get_current_user
from app.domain.defaults import DEFAULT_FIELDS, DEFAULT_PROMPT
from app.domain.models import ProviderName
from app.repos import configs as configs_repo
from app.repos.db import session_scope


log = logging.getLogger(__name__)

DEFAULT_CONFIG_NAME = "Default"


def seed_default_config() -> None:
    """Idempotently create the seed 'Default' config. Logs and skips if it already exists."""
    with session_scope() as session:
        existing = configs_repo.get_config_by_name(session, DEFAULT_CONFIG_NAME)
        if existing is not None:
            log.info("Seed: %r already exists (id=%s), skipping.", DEFAULT_CONFIG_NAME, existing.id)
            return

        created = configs_repo.create_config(
            session,
            name=DEFAULT_CONFIG_NAME,
            description="Bundled starting prompt + 22-field schema. Lifted from concrete-tracker-prompt-lab and concrete-trakcer-prompts-comparison.",
            prompt=DEFAULT_PROMPT,
            fields=DEFAULT_FIELDS,
            provider=ProviderName.MISTRAL_2505,
            provider_options={},
            notes="Seed v1 — first checkpoint, do not delete.",
            created_by=get_current_user(),
        )
        log.info("Seed: created %r v%d (id=%s)", created.config_name, created.version, created.config_id)
