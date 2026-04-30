from datetime import datetime
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class FieldType(str, Enum):
    STRING = "string"
    NUMERIC = "numeric"
    DATE = "date"
    TIME = "time"
    ENUM = "enum"
    BOOLEAN = "boolean"


class FieldSpec(BaseModel):
    name: str
    label: str
    description: str
    example: Optional[str] = None
    type: FieldType = FieldType.STRING


class ProviderName(str, Enum):
    MISTRAL_2505 = "mistral_2505"
    MISTRAL_2512 = "mistral_2512"
    AZURE_DI_GPT = "azure_di_gpt"


class ConfigVersionData(BaseModel):
    config_id: UUID
    config_name: str
    version: int
    prompt: str
    fields: list[FieldSpec]
    provider: ProviderName
    provider_options: dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None
    created_by: str
    created_at: datetime


class Extraction(BaseModel):
    fields: dict[str, Any]
    raw_text: Optional[str] = None
    raw_response: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int
    cache_hit: bool = False


class RunRecord(BaseModel):
    id: UUID
    config_version_id: UUID
    blob_path: str
    filename: str
    extraction: Optional[dict[str, Any]] = None
    ocr_text: Optional[str] = None
    latency_ms: Optional[int] = None
    error: Optional[str] = None
    created_by: str
    created_at: datetime
