from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+psycopg://promptify:promptify@localhost:5432/promptify"

    # Object storage
    azure_storage_connection_string: str = ""
    blob_container_documents: str = "documents"
    blob_container_datasets: str = "datasets"

    # Auth
    local_dev_user: str = "local-dev@example.com"

    # Mistral OCR (Foundry)
    azure_mistralocr_endpoint: str = ""
    azure_mistralocr_api_key: str = ""

    # Azure Document Intelligence
    azure_document_intelligence_endpoint: str = ""
    azure_document_intelligence_key: str = ""

    # Azure OpenAI
    azure_openai_endpoint: str = ""
    azure_openai_api_key: str = ""
    azure_openai_deployment_name: str = "scanbeton-gpt-4.1-mini"
    azure_openai_api_version: str = "2024-12-01-preview"

    # Behaviour
    seed_on_startup: bool = True
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
