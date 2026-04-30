import base64
import json
import time
from typing import Any

import httpx

from app.core.config import get_settings
from app.domain.models import Extraction, FieldSpec, FieldType, ProviderName
from app.providers.base import OCRProvider, ProviderError


_FIELD_TYPE_TO_JSON: dict[FieldType, list[str]] = {
    FieldType.STRING: ["string", "null"],
    FieldType.NUMERIC: ["number", "null"],
    FieldType.DATE: ["string", "null"],
    FieldType.TIME: ["string", "null"],
    FieldType.ENUM: ["string", "null"],
    FieldType.BOOLEAN: ["boolean", "null"],
}


def build_json_schema(fields: list[FieldSpec]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            f.name: {
                "type": _FIELD_TYPE_TO_JSON[f.type],
                "description": f.description + (f' (e.g. "{f.example}")' if f.example else ""),
            }
            for f in fields
        },
        "required": [f.name for f in fields],
    }


class MistralOCRProvider(OCRProvider):
    """Single-call OCR + structured extraction via Foundry-hosted Mistral models."""

    def __init__(self, name: ProviderName, model: str):
        self.name = name
        self.model = model

    def run(
        self,
        file_bytes: bytes,
        mime_type: str,
        prompt: str,
        fields: list[FieldSpec],
        options: dict[str, Any],
    ) -> Extraction:
        s = get_settings()
        if not s.azure_mistralocr_endpoint:
            raise ProviderError("AZURE_MISTRALOCR_ENDPOINT is not set.")
        if not s.azure_mistralocr_api_key:
            raise ProviderError("AZURE_MISTRALOCR_API_KEY is not set.")

        is_pdf = mime_type == "application/pdf"
        b64 = base64.b64encode(file_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{b64}"

        payload: dict[str, Any] = {
            "model": self.model,
            "document": {
                "type": "document_url" if is_pdf else "image_url",
                ("document_url" if is_pdf else "image_url"): data_url,
            },
            "document_annotation_prompt": prompt,
            "document_annotation_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "delivery_note_extraction",
                    "schema": build_json_schema(fields),
                    "strict": False,
                },
            },
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {s.azure_mistralocr_api_key}",
            "api-key": s.azure_mistralocr_api_key,
        }

        t0 = time.perf_counter()
        try:
            resp = httpx.post(
                s.azure_mistralocr_endpoint, json=payload, headers=headers, timeout=120
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise ProviderError(f"HTTP {e.response.status_code}: {e.response.text[:500]}") from e
        except httpx.RequestError as e:
            raise ProviderError(f"Request failed: {e}") from e
        latency_ms = int((time.perf_counter() - t0) * 1000)

        data = resp.json()

        # Aggregate page text
        pages = data.get("pages", []) or []
        if pages:
            parts: list[str] = []
            for i, p in enumerate(pages):
                prefix = f"--- Page {i + 1} ---\n" if len(pages) > 1 else ""
                parts.append(prefix + (p.get("markdown") or p.get("text") or ""))
            full_text: str | None = "\n\n".join(parts)
        else:
            full_text = data.get("text") or None

        extracted: dict[str, Any] = {}
        ann = data.get("document_annotation")
        if ann:
            try:
                parsed = json.loads(ann) if isinstance(ann, str) else ann
                if isinstance(parsed, dict):
                    extracted = parsed
            except json.JSONDecodeError:
                extracted = {"_raw": ann}

        return Extraction(
            fields=extracted,
            raw_text=full_text,
            raw_response=data,
            latency_ms=latency_ms,
        )


def make_mistral_2505() -> MistralOCRProvider:
    return MistralOCRProvider(ProviderName.MISTRAL_2505, "mistral-document-ai-2505")


def make_mistral_2512() -> MistralOCRProvider:
    return MistralOCRProvider(ProviderName.MISTRAL_2512, "mistral-document-ai-2512")
