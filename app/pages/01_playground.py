import pandas as pd
import streamlit as st

from app.core.seed import DEFAULT_CONFIG_NAME
from app.domain.defaults import DEFAULT_FIELDS, DEFAULT_PROMPT
from app.domain.models import FieldSpec, FieldType, ProviderName
from app.providers.base import ProviderError
from app.providers.registry import list_provider_names
from app.repos import configs as configs_repo
from app.repos.db import session_scope
from app.services.runner import RunRequest, run_single


st.set_page_config(page_title="Playground · Promptify", layout="wide")
st.title("Playground")
st.caption("Upload one BL, edit prompt + fields, pick a model, run.")


# ── Load default config from DB (seeded on startup) ─────────────────────────
def _load_default():
    with session_scope() as session:
        return configs_repo.get_latest_version(session, DEFAULT_CONFIG_NAME)


if "pg_loaded" not in st.session_state:
    default = _load_default()
    if default is not None:
        st.session_state.pg_prompt = default.prompt
        st.session_state.pg_fields = [f.model_dump(mode="json") for f in default.fields]
        st.session_state.pg_provider = default.provider.value
        st.session_state.pg_config_version_id = str(default.config_id)
    else:
        # Fallback to in-process defaults if DB not yet seeded.
        st.session_state.pg_prompt = DEFAULT_PROMPT
        st.session_state.pg_fields = [f.model_dump(mode="json") for f in DEFAULT_FIELDS]
        st.session_state.pg_provider = ProviderName.MISTRAL_2505.value
        st.session_state.pg_config_version_id = None
    st.session_state.pg_result = None
    st.session_state.pg_loaded = True


# ── Layout ──────────────────────────────────────────────────────────────────
left, right = st.columns([5, 4], gap="large")

with left:
    st.subheader("1 · Document")
    uploaded = st.file_uploader(
        "Upload a BL", type=["pdf", "png", "jpg", "jpeg", "webp"], label_visibility="collapsed"
    )

    st.subheader("2 · Provider")
    provider_options = [p.value for p in list_provider_names()]
    st.session_state.pg_provider = st.selectbox(
        "OCR backend",
        options=provider_options,
        index=provider_options.index(st.session_state.pg_provider),
        format_func=lambda v: {
            "mistral_2505": "Mistral OCR · 2505 (May 2025)",
            "mistral_2512": "Mistral OCR · 2512 (Dec 2025)",
            "azure_di_gpt": "Azure DI + GPT-4.1-mini",
        }.get(v, v),
    )

    skip_cache = st.checkbox("Skip cache lookup", value=False, help="Force a fresh API call.")

    st.subheader("3 · Prompt")
    st.session_state.pg_prompt = st.text_area(
        "Extraction prompt", value=st.session_state.pg_prompt, height=260, label_visibility="collapsed"
    )

    st.subheader("4 · Fields")
    field_types = [t.value for t in FieldType]
    updated: list[dict] = []
    to_remove: int | None = None
    for i, field in enumerate(st.session_state.pg_fields):
        with st.expander(f"{field['label']}  (`{field['name']}`)", expanded=False):
            c1, c2 = st.columns(2)
            name = c1.text_input("Key name", value=field["name"], key=f"pg_name_{i}")
            label = c2.text_input("Label", value=field["label"], key=f"pg_label_{i}")
            ftype = st.selectbox(
                "Type",
                options=field_types,
                index=field_types.index(field.get("type", "string")),
                key=f"pg_type_{i}",
            )
            description = st.text_area(
                "Description", value=field["description"], height=80, key=f"pg_desc_{i}"
            )
            example = st.text_input("Example value", value=field.get("example") or "", key=f"pg_ex_{i}")
            if st.button("Remove", key=f"pg_rm_{i}"):
                to_remove = i
            updated.append(
                {
                    "name": name,
                    "label": label,
                    "description": description,
                    "example": example or None,
                    "type": ftype,
                }
            )
    st.session_state.pg_fields = updated
    if to_remove is not None:
        st.session_state.pg_fields.pop(to_remove)
        st.rerun()

    if st.button("➕ Add field", use_container_width=True):
        st.session_state.pg_fields.append(
            {"name": "new_field", "label": "New field", "description": "", "example": None, "type": "string"}
        )
        st.rerun()


# ── Right column: run + results ─────────────────────────────────────────────
with right:
    st.subheader("Run")
    run_disabled = uploaded is None or not st.session_state.pg_fields
    if st.button("▶ Run", disabled=run_disabled, type="primary", use_container_width=True):
        try:
            file_bytes = uploaded.read()
            fields = [FieldSpec(**f) for f in st.session_state.pg_fields]
            req = RunRequest(
                file_bytes=file_bytes,
                filename=uploaded.name,
                prompt=st.session_state.pg_prompt,
                fields=fields,
                provider=ProviderName(st.session_state.pg_provider),
                provider_options={},
                skip_cache_lookup=skip_cache,
            )
            with st.spinner("Calling OCR…"), session_scope() as session:
                extraction = run_single(session, req)
            st.session_state.pg_result = {
                "extraction": extraction.fields,
                "raw_text": extraction.raw_text,
                "latency_ms": extraction.latency_ms,
                "cache_hit": extraction.cache_hit,
                "provider": st.session_state.pg_provider,
                "field_labels": {f.name: f.label for f in fields},
            }
        except ProviderError as e:
            st.error(f"Provider error: {e}")
        except Exception as e:
            st.exception(e)

    res = st.session_state.pg_result
    if res:
        badges = []
        badges.append(f"`{res['provider']}`")
        if res["cache_hit"]:
            badges.append("🟢 cache hit")
        else:
            badges.append(f"⏱ {res['latency_ms']} ms")
        st.markdown(" · ".join(badges))

        st.subheader("Extraction")
        rows = [
            {"Field": res["field_labels"].get(k, k), "Value": v if v is not None else "—"}
            for k, v in (res["extraction"] or {}).items()
        ]
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.warning("No structured extraction returned. Check your prompt and fields.")

        with st.expander("Raw extraction JSON"):
            st.json(res["extraction"])
        with st.expander("OCR raw text"):
            st.code(res["raw_text"] or "(no text returned)", language="")
    else:
        st.info("Upload a BL on the left and click **▶ Run**.")
