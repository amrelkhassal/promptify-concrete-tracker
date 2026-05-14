import unicodedata
from io import BytesIO
from uuid import UUID, uuid4

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

FIELD_UI_ID = "_ui_id"
FIELD_COLUMNS = ["name", "label", "type", "description", "example"]
IMPORT_COLUMN_ALIASES = {
    "name": {"name", "key", "field", "fieldname", "field_name", "field name", "nom", "cle", "clé"},
    "label": {"label", "libelle", "libellé", "displayname", "display_name", "display name"},
    "type": {"type", "fieldtype", "field_type", "field type"},
    "description": {"description", "desc", "instruction", "instructions"},
    "example": {"example", "exemple", "sample"},
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _list_configs():
    with session_scope() as s:
        return configs_repo.list_configs(s)


def _load_version(config_name: str):
    with session_scope() as s:
        return configs_repo.get_latest_version(s, config_name)


def _with_ui_id(field: dict) -> dict:
    """Attach a stable UI id so Streamlit widget state survives insert/remove."""
    out = dict(field)
    out.setdefault(FIELD_UI_ID, uuid4().hex)
    return out


def _field_payload(field: dict) -> dict:
    return {k: v for k, v in field.items() if k != FIELD_UI_ID}


def _field_specs_from_state() -> list[FieldSpec]:
    return [FieldSpec(**_field_payload(f)) for f in st.session_state.pg_fields]


def _normalize_import_header(value: object) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or "").strip().lower())
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return ascii_text.replace("-", " ").replace(".", " ").strip()


def _canonical_import_column(column: object) -> str | None:
    normalized = _normalize_import_header(column)
    compact = normalized.replace(" ", "").replace("_", "")
    for field_name, aliases in IMPORT_COLUMN_ALIASES.items():
        alias_keys = {_normalize_import_header(alias) for alias in aliases}
        alias_compact_keys = {alias.replace(" ", "").replace("_", "") for alias in alias_keys}
        if normalized in alias_keys or compact in alias_compact_keys:
            return field_name
    return None


def _normalize_import_fields(raw_df: pd.DataFrame) -> list[dict]:
    renamed: dict[object, str] = {}
    for col in raw_df.columns:
        canonical = _canonical_import_column(col)
        if canonical and canonical not in renamed.values():
            renamed[col] = canonical

    if "name" not in renamed.values():
        raise ValueError("Import file must include a field key column such as 'name', 'key', or 'field'.")

    df = raw_df.rename(columns=renamed)
    out: list[dict] = []
    field_types = {t.value for t in FieldType}

    for _, row in df.fillna("").iterrows():
        name = str(row.get("name", "")).strip()
        if not name:
            continue

        label = str(row.get("label", "")).strip() or name
        ftype = str(row.get("type", "")).strip() or FieldType.STRING.value
        if ftype not in field_types:
            ftype = FieldType.STRING.value

        out.append(
            _with_ui_id(
                {
                    "name": name,
                    "label": label,
                    "type": ftype,
                    "description": str(row.get("description", "")).strip(),
                    "example": str(row.get("example", "")).strip() or None,
                }
            )
        )

    if not out:
        raise ValueError("Import file did not contain any usable field rows.")
    return out


def _read_optional_config_sheet(sheets: dict[str, pd.DataFrame]) -> dict[str, str]:
    config_sheet = next(
        (df for name, df in sheets.items() if _normalize_import_header(name) == "config"),
        None,
    )
    if config_sheet is None or config_sheet.empty:
        return {}
    if len(config_sheet.columns) < 2:
        return {}

    df = config_sheet.fillna("")
    if {"key", "value"}.issubset({_normalize_import_header(c) for c in df.columns}):
        key_col = next(c for c in df.columns if _normalize_import_header(c) == "key")
        value_col = next(c for c in df.columns if _normalize_import_header(c) == "value")
    else:
        key_col, value_col = df.columns[:2]

    out: dict[str, str] = {}
    for _, row in df.iterrows():
        key = _normalize_import_header(row.get(key_col))
        value = str(row.get(value_col, "")).strip()
        if key and value:
            out[key] = value
    return out


def _read_config_import(uploaded_file) -> tuple[list[dict], str | None, str | None]:
    uploaded_file.seek(0)
    filename = uploaded_file.name.lower()

    if filename.endswith(".csv"):
        fields = _normalize_import_fields(pd.read_csv(uploaded_file, dtype=str))
        return fields, None, None

    sheets = pd.read_excel(uploaded_file, sheet_name=None, dtype=str)
    fields_sheet = next(
        (df for name, df in sheets.items() if _normalize_import_header(name) == "fields"),
        next(iter(sheets.values())),
    )
    imported_fields = _normalize_import_fields(fields_sheet)
    imported_config = _read_optional_config_sheet(sheets)

    prompt = imported_config.get("prompt")
    provider = imported_config.get("provider")
    if provider and provider not in {p.value for p in ProviderName}:
        provider = None

    return imported_fields, prompt, provider


def _template_fields_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "name": "deliveryNumber",
                "label": "N° bon de livraison",
                "type": "string",
                "description": "Delivery note number.",
                "example": "123456",
            },
            {
                "name": "quantity",
                "label": "Quantité",
                "type": "numeric",
                "description": "Delivered volume as a plain number.",
                "example": "7.5",
            },
            {
                "name": "dateLivraison",
                "label": "Date de livraison",
                "type": "date",
                "description": "Delivery date in dd/mm/yyyy.",
                "example": "15/03/2024",
            },
        ],
        columns=FIELD_COLUMNS,
    )


def _template_csv_bytes() -> bytes:
    return _template_fields_df().to_csv(index=False).encode("utf-8")


def _template_xlsx_bytes() -> bytes:
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        _template_fields_df().to_excel(writer, sheet_name="fields", index=False)
        pd.DataFrame(
            [
                {"key": "prompt", "value": "Paste an optional full extraction prompt here."},
                {"key": "provider", "value": ProviderName.MISTRAL_2505.value},
            ]
        ).to_excel(writer, sheet_name="config", index=False)
    return buf.getvalue()


def _bump_fields_editor_revision():
    st.session_state.pg_fields_editor_revision = st.session_state.get("pg_fields_editor_revision", 0) + 1


def _apply_version(ver):
    st.session_state.pg_prompt = ver.prompt
    st.session_state.pg_fields = [_with_ui_id(f.model_dump(mode="json")) for f in ver.fields]
    st.session_state.pg_provider = ver.provider.value
    st.session_state.pg_active_config_name = ver.config_name
    st.session_state.pg_active_config_id = str(ver.config_id)
    st.session_state.pg_result = None
    _bump_fields_editor_revision()


def _reset_editor_to_defaults():
    st.session_state.pg_prompt = DEFAULT_PROMPT
    st.session_state.pg_fields = [_with_ui_id(f.model_dump(mode="json")) for f in DEFAULT_FIELDS]
    st.session_state.pg_provider = ProviderName.MISTRAL_2505.value
    st.session_state.pg_active_config_name = None
    st.session_state.pg_active_config_id = None
    st.session_state.pg_result = None
    _bump_fields_editor_revision()


# ── Bootstrap session state ──────────────────────────────────────────────────

if "pg_loaded" not in st.session_state:
    ver = _load_version(DEFAULT_CONFIG_NAME)
    if ver:
        _apply_version(ver)
    else:
        _reset_editor_to_defaults()
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

    chosen = st.selectbox("Load config", options=select_options, index=0, label_visibility="collapsed")
    if chosen != active_label:
        ver = _load_version(chosen)
        if ver:
            _apply_version(ver)
            st.rerun()

    if st.session_state.get("pg_flash_success"):
        st.success(st.session_state.pop("pg_flash_success"))

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
    with st.expander("Import fields from CSV/XLSX"):
        col_csv, col_xlsx = st.columns(2)
        col_csv.download_button(
            "Download CSV template",
            data=_template_csv_bytes(),
            file_name="promptify_config_fields_template.csv",
            mime="text/csv",
            use_container_width=True,
        )
        col_xlsx.download_button(
            "Download XLSX template",
            data=_template_xlsx_bytes(),
            file_name="promptify_config_template.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
        import_file = st.file_uploader("Config fields file", type=["csv", "xlsx"], key="pg_import_fields_file")
        import_mode = st.radio("Import mode", ["Replace table", "Append to table"], horizontal=True)
        if st.button("Import into table", disabled=import_file is None, use_container_width=True):
            try:
                imported_fields, imported_prompt, imported_provider = _read_config_import(import_file)
                if import_mode == "Append to table":
                    st.session_state.pg_fields = st.session_state.pg_fields + imported_fields
                else:
                    st.session_state.pg_fields = imported_fields

                if imported_prompt:
                    st.session_state.pg_prompt = imported_prompt
                if imported_provider:
                    st.session_state.pg_provider = imported_provider

                _bump_fields_editor_revision()
                st.session_state.pg_flash_success = f"Imported {len(imported_fields)} field(s)."
                st.rerun()
            except Exception as e:
                st.error(f"Import failed: {e}")

    fields_df = pd.DataFrame([_field_payload(f) for f in st.session_state.pg_fields])
    fields_df = fields_df.reindex(columns=FIELD_COLUMNS).fillna("")
    fields_df = fields_df.astype({col: "string" for col in FIELD_COLUMNS})

    edited_fields_df = st.data_editor(
        fields_df,
        key=f"pg_fields_editor_{st.session_state.get('pg_fields_editor_revision', 0)}",
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_order=FIELD_COLUMNS,
        column_config={
            "name": st.column_config.TextColumn("Key", required=True, width="medium"),
            "label": st.column_config.TextColumn("Label", required=True, width="medium"),
            "type": st.column_config.SelectboxColumn("Type", options=field_types, required=True, width="small"),
            "description": st.column_config.TextColumn("Description", width="large"),
            "example": st.column_config.TextColumn("Example", width="medium"),
        },
    )

    updated_fields: list[dict] = []
    invalid_rows: list[int] = []
    for idx, row in edited_fields_df.fillna("").iterrows():
        name = str(row.get("name", "")).strip()
        label = str(row.get("label", "")).strip()
        ftype = str(row.get("type", "")).strip() or FieldType.STRING.value
        description = str(row.get("description", "")).strip()
        example = str(row.get("example", "")).strip()

        if not any([name, label, description, example]):
            continue
        if not name or not label or ftype not in field_types:
            invalid_rows.append(idx + 1)
            continue

        updated_fields.append(
            _with_ui_id(
                {
                    "name": name,
                    "label": label,
                    "description": description,
                    "example": example or None,
                    "type": ftype,
                }
            )
        )

    st.session_state.pg_fields = updated_fields
    if invalid_rows:
        st.warning(
            "Rows with missing Key, Label, or Type are ignored until fixed: "
            + ", ".join(str(i) for i in invalid_rows)
        )

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
                    fields = _field_specs_from_state()
                    with session_scope() as s:
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
                    _apply_version(ver)
                    st.session_state.pg_flash_success = f"Saved as **{active_name}** v{ver.version}."
                    st.rerun()
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
                fields = _field_specs_from_state()
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
                _apply_version(ver)
                st.session_state.pg_flash_success = f"Created **{ver.config_name}** v1."
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
            fields = _field_specs_from_state()
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
