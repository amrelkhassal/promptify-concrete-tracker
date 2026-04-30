import pandas as pd
import streamlit as st

from app.core.auth import get_current_user
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

PROVIDER_LABELS = {
    "mistral_2505": "Mistral OCR · 2505 (May 2025)",
    "mistral_2512": "Mistral OCR · 2512 (Dec 2025)",
    "azure_di_gpt": "Azure DI + GPT-4.1-mini",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _list_configs():
    with session_scope() as s:
        return configs_repo.list_configs(s)


def _load_version(config_name: str):
    with session_scope() as s:
        return configs_repo.get_latest_version(s, config_name)


def _apply_version(ver):
    st.session_state.pg_prompt = ver.prompt
    st.session_state.pg_fields = [f.model_dump(mode="json") for f in ver.fields]
    st.session_state.pg_provider = ver.provider.value
    st.session_state.pg_active_config_name = ver.config_name
    st.session_state.pg_active_config_id = str(ver.config_id)


# ── Bootstrap session state ──────────────────────────────────────────────────

if "pg_loaded" not in st.session_state:
    ver = _load_version(DEFAULT_CONFIG_NAME)
    if ver:
        _apply_version(ver)
    else:
        st.session_state.pg_prompt = DEFAULT_PROMPT
        st.session_state.pg_fields = [f.model_dump(mode="json") for f in DEFAULT_FIELDS]
        st.session_state.pg_provider = ProviderName.MISTRAL_2505.value
        st.session_state.pg_active_config_name = None
        st.session_state.pg_active_config_id = None
    st.session_state.pg_result = None
    st.session_state.pg_loaded = True


# ── Layout ──────────────────────────────────────────────────────────────────
left, right = st.columns([5, 4], gap="large")

with left:
    # ── 1. Load config ────────────────────────────────────────────────────────
    st.subheader("1 · Config")
    all_configs = _list_configs()
    config_names = [c["data"].config_name for c in all_configs]

    active_name = st.session_state.pg_active_config_name
    active_label = f"✏️ draft (based on {active_name})" if active_name else "✏️ draft"
    select_options = [active_label] + config_names
    try:
        current_idx = select_options.index(active_name) if active_name in select_options else 0
    except ValueError:
        current_idx = 0

    chosen = st.selectbox("Load config", options=select_options, index=current_idx, label_visibility="collapsed")
    if chosen != active_label and chosen != active_name:
        ver = _load_version(chosen)
        if ver:
            _apply_version(ver)
            st.session_state.pg_result = None
            st.rerun()

    if active_name:
        st.caption(f"Loaded: **{active_name}** — edits below are unsaved until you save.")

    st.divider()

    # ── 2. Document + Provider ────────────────────────────────────────────────
    st.subheader("2 · Document")
    uploaded = st.file_uploader(
        "Upload a BL", type=["pdf", "png", "jpg", "jpeg", "webp"], label_visibility="collapsed"
    )

    st.subheader("3 · Provider")
    provider_options = [p.value for p in list_provider_names()]
    current_provider_idx = provider_options.index(st.session_state.pg_provider) if st.session_state.pg_provider in provider_options else 0
    st.session_state.pg_provider = st.selectbox(
        "OCR backend",
        options=provider_options,
        index=current_provider_idx,
        format_func=lambda v: PROVIDER_LABELS.get(v, v),
        label_visibility="collapsed",
    )
    skip_cache = st.checkbox("Skip cache lookup", value=False, help="Force a fresh API call.")

    st.divider()

    # ── 3. Prompt ─────────────────────────────────────────────────────────────
    st.subheader("4 · Prompt")
    st.session_state.pg_prompt = st.text_area(
        "Extraction prompt", value=st.session_state.pg_prompt, height=260, label_visibility="collapsed"
    )

    st.divider()

    # ── 4. Fields ─────────────────────────────────────────────────────────────
    st.subheader("5 · Fields")
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
            updated.append({
                "name": name, "label": label, "description": description,
                "example": example or None, "type": ftype,
            })
    st.session_state.pg_fields = updated
    if to_remove is not None:
        st.session_state.pg_fields.pop(to_remove)
        st.rerun()
    if st.button("➕ Add field", use_container_width=True):
        st.session_state.pg_fields.append(
            {"name": "new_field", "label": "New field", "description": "", "example": None, "type": "string"}
        )
        st.rerun()

    st.divider()

    # ── 5. Save ───────────────────────────────────────────────────────────────
    st.subheader("6 · Save")
    tab_version, tab_new = st.tabs(["New version of existing", "Brand-new config"])

    with tab_version:
        if active_name:
            st.caption(f"Adds a new version to **{active_name}**.")
            notes_v = st.text_input("Notes (optional)", placeholder="What changed?", key="pg_notes_v")
            if st.button("💾 Save as new version", use_container_width=True, key="pg_save_version"):
                try:
                    fields = [FieldSpec(**f) for f in st.session_state.pg_fields]
                    with session_scope() as s:
                        from uuid import UUID
                        ver = configs_repo.add_version(
                            s,
                            config_id=UUID(st.session_state.pg_active_config_id),
                            prompt=st.session_state.pg_prompt,
                            fields=fields,
                            provider=ProviderName(st.session_state.pg_provider),
                            provider_options={},
                            notes=notes_v or None,
                            created_by=get_current_user(),
                        )
                    st.success(f"Saved as **{active_name}** v{ver.version}.")
                except Exception as e:
                    st.error(f"Save failed: {e}")
        else:
            st.info("Load a config first to save a new version of it.")

    with tab_new:
        new_name = st.text_input("Config name", placeholder="e.g. Saudi worksites", key="pg_new_name")
        new_desc = st.text_input("Description (optional)", key="pg_new_desc")
        notes_n = st.text_input("Notes (optional)", placeholder="Initial version", key="pg_notes_n")
        if st.button("💾 Create new config", disabled=not new_name.strip(), use_container_width=True, key="pg_save_new"):
            try:
                fields = [FieldSpec(**f) for f in st.session_state.pg_fields]
                with session_scope() as s:
                    ver = configs_repo.create_config(
                        s,
                        name=new_name.strip(),
                        description=new_desc.strip() or None,
                        prompt=st.session_state.pg_prompt,
                        fields=fields,
                        provider=ProviderName(st.session_state.pg_provider),
                        provider_options={},
                        notes=notes_n or None,
                        created_by=get_current_user(),
                    )
                st.session_state.pg_active_config_name = ver.config_name
                st.session_state.pg_active_config_id = str(ver.config_id)
                st.success(f"Created **{ver.config_name}** v1.")
                st.rerun()
            except Exception as e:
                st.error(f"Save failed: {e}")


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
        badges = [f"`{PROVIDER_LABELS.get(res['provider'], res['provider'])}`"]
        badges.append("🟢 cache hit" if res["cache_hit"] else f"⏱ {res['latency_ms']} ms")
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
