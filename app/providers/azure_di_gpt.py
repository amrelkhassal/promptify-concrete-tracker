import json
import time
from typing import Any

from app.core.config import get_settings
from app.domain.models import Extraction, FieldSpec, FieldType, ProviderName
from app.providers.base import OCRProvider, ProviderError


_FIELD_TYPE_TO_GPT: dict[FieldType, str] = {
    FieldType.STRING: "string",
    FieldType.NUMERIC: "number",
    FieldType.DATE: "string",
    FieldType.TIME: "string",
    FieldType.ENUM: "string",
    FieldType.BOOLEAN: "boolean",
}


def build_function_schema(fields: list[FieldSpec]) -> dict[str, Any]:
    return {
        "name": "extractDeliveryNoteData",
        "description": "Extract structured fields from a concrete delivery note.",
        "parameters": {
            "type": "object",
            "properties": {
                f.name: {
                    "type": _FIELD_TYPE_TO_GPT[f.type],
                    "description": f.description + (f' (e.g. "{f.example}")' if f.example else ""),
                }
                for f in fields
            },
            "required": [],
        },
    }


class AzureDIGPTProvider(OCRProvider):
    """Two-step: Azure Document Intelligence (prebuilt-layout) → Azure OpenAI (function call)."""

    name = ProviderName.AZURE_DI_GPT

    def run(
        self,
        file_bytes: bytes,
        mime_type: str,
        prompt: str,
        fields: list[FieldSpec],
        options: dict[str, Any],
    ) -> Extraction:
        try:
            from azure.ai.documentintelligence import DocumentIntelligenceClient
            from azure.core.credentials import AzureKeyCredential
            from openai import AzureOpenAI
        except ImportError as e:
            raise ProviderError(f"Missing package: {e}") from e

        s = get_settings()
        if not s.azure_document_intelligence_endpoint or not s.azure_document_intelligence_key:
            raise ProviderError("AZURE_DOCUMENT_INTELLIGENCE_* settings are not set.")
        if not s.azure_openai_endpoint or not s.azure_openai_api_key:
            raise ProviderError("AZURE_OPENAI_* settings are not set.")

        deployment = options.get("gpt_deployment") or s.azure_openai_deployment_name
        api_version = options.get("api_version") or s.azure_openai_api_version

        # ── Step 1: Azure DI → raw text ─────────────────────────────────────
        t0 = time.perf_counter()
        try:
            di_client = DocumentIntelligenceClient(
                endpoint=s.azure_document_intelligence_endpoint,
                credential=AzureKeyCredential(s.azure_document_intelligence_key),
            )
            poller = di_client.begin_analyze_document(
                "prebuilt-layout",
                body=file_bytes,
                content_type="application/octet-stream",
            )
            di_result = poller.result()
            document_text = di_result.content or ""
        except Exception as e:
            raise ProviderError(f"Azure DI failed: {e}") from e

        # ── Step 2: Azure OpenAI function calling ───────────────────────────
        try:
            oai_client = AzureOpenAI(
                api_key=s.azure_openai_api_key,
                azure_endpoint=s.azure_openai_endpoint,
                api_version=api_version,
            )
            tool = {"type": "function", "function": build_function_schema(fields)}
            response = oai_client.chat.completions.create(
                model=deployment,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": document_text},
                ],
                tools=[tool],
                tool_choice={"type": "function", "function": {"name": "extractDeliveryNoteData"}},
            )
            tool_calls = response.choices[0].message.tool_calls or []
            if not tool_calls:
                raise ProviderError("GPT returned no tool call.")
            extracted = json.loads(tool_calls[0].function.arguments)
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"Azure OpenAI failed: {e}") from e

        latency_ms = int((time.perf_counter() - t0) * 1000)
        return Extraction(
            fields=extracted,
            raw_text=document_text,
            raw_response={"di_pages": len(getattr(di_result, "pages", []) or [])},
            latency_ms=latency_ms,
        )


def make_azure_di_gpt() -> AzureDIGPTProvider:
    return AzureDIGPTProvider()
