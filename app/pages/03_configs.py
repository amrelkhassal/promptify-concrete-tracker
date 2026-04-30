import difflib
import json
from uuid import UUID

import streamlit as st

from app.core.auth import get_current_user
from app.domain.models import FieldSpec, ProviderName
from app.repos import configs as configs_repo
from app.repos.db import Config, session_scope


st.set_page_config(page_title="Configs · Promptify", layout="wide")
st.title("Configs")
st.caption("Manage saved prompt + field configs and their version history.")

PROVIDER_LABELS = {
    "mistral_2505": "Mistral 2505",
    "mistral_2512": "Mistral 2512",
    "azure_di_gpt": "Azure DI + GPT",
}


# ── List all configs ──────────────────────────────────────────────────────────

with session_scope() as s:
    all_configs = configs_repo.list_configs(s)

if not all_configs:
    st.info("No configs yet. Create one in the Playground.")
    st.stop()

# Build index table
index_rows = []
for c in all_configs:
    d = c["data"]
    index_rows.append({
        "Name": d.config_name,
        "Latest v": d.version,
        "Provider": PROVIDER_LABELS.get(d.provider.value, d.provider.value),
        "Fields": len(d.fields),
        "Last saved by": d.created_by,
        "Archived": c["config"].is_archived,
    })

import pandas as pd
df = pd.DataFrame(index_rows)
st.dataframe(df, use_container_width=True, hide_index=True)

st.divider()


# ── Select a config to inspect ────────────────────────────────────────────────

config_names = [c["data"].config_name for c in all_configs]
selected_name = st.selectbox("Select config to inspect", options=config_names)

with session_scope() as s:
    cfg_row = next((c for c in all_configs if c["data"].config_name == selected_name), None)
    if cfg_row is None:
        st.stop()
    config_id: UUID = cfg_row["config"].id
    versions = configs_repo.list_versions(s, config_id)

if not versions:
    st.warning("No versions found.")
    st.stop()

latest = versions[0]

# ── Config header ─────────────────────────────────────────────────────────────

col_info, col_actions = st.columns([3, 1])
with col_info:
    desc = cfg_row["config"].description
    if desc:
        st.caption(desc)
    st.markdown(
        f"**{len(versions)} version(s)** · latest: v{latest.version} "
        f"· provider: `{PROVIDER_LABELS.get(latest.provider.value, latest.provider.value)}` "
        f"· {len(latest.fields)} fields"
    )

with col_actions:
    archive_label = "Unarchive" if cfg_row["config"].is_archived else "Archive"
    if st.button(archive_label, use_container_width=True):
        with session_scope() as s:
            cfg_obj = s.get(Config, config_id)
            if cfg_obj:
                cfg_obj.is_archived = not cfg_obj.is_archived
        st.rerun()

    export_payload = {
        "config_name": latest.config_name,
        "version": latest.version,
        "provider": latest.provider.value,
        "prompt": latest.prompt,
        "fields": [f.model_dump(mode="json") for f in latest.fields],
        "provider_options": latest.provider_options,
    }
    st.download_button(
        "⬇ Export JSON",
        data=json.dumps(export_payload, ensure_ascii=False, indent=2),
        file_name=f"{selected_name.lower().replace(' ', '_')}_v{latest.version}.json",
        mime="application/json",
        use_container_width=True,
    )

st.divider()


# ── Version history ───────────────────────────────────────────────────────────

st.subheader("Version history")

ver_rows = [
    {
        "Version": v.version,
        "Provider": PROVIDER_LABELS.get(v.provider.value, v.provider.value),
        "Fields": len(v.fields),
        "Notes": v.notes or "—",
        "Saved by": v.created_by,
        "Date": v.created_at.strftime("%Y-%m-%d %H:%M"),
    }
    for v in versions
]
st.dataframe(pd.DataFrame(ver_rows), use_container_width=True, hide_index=True)

st.divider()


# ── Version diff ──────────────────────────────────────────────────────────────

st.subheader("Compare two versions")

ver_nums = [v.version for v in versions]
if len(ver_nums) < 2:
    st.info("Need at least 2 versions to compare.")
else:
    c1, c2 = st.columns(2)
    with c1:
        v_a = st.selectbox("Version A (older)", options=ver_nums, index=len(ver_nums) - 1, key="diff_a")
    with c2:
        v_b = st.selectbox("Version B (newer)", options=ver_nums, index=0, key="diff_b")

    if v_a != v_b:
        ver_a = next(v for v in versions if v.version == v_a)
        ver_b = next(v for v in versions if v.version == v_b)

        # ── Prompt diff ──────────────────────────────────────────────────────
        with st.expander(f"Prompt diff  (v{v_a} → v{v_b})", expanded=True):
            a_lines = ver_a.prompt.splitlines(keepends=True)
            b_lines = ver_b.prompt.splitlines(keepends=True)
            diff = list(difflib.unified_diff(a_lines, b_lines, fromfile=f"v{v_a}", tofile=f"v{v_b}"))
            if diff:
                st.code("".join(diff), language="diff")
            else:
                st.success("Prompts are identical.")

        # ── Fields diff ───────────────────────────────────────────────────────
        with st.expander(f"Fields diff  (v{v_a} → v{v_b})", expanded=True):
            a_fields = {f.name: f for f in ver_a.fields}
            b_fields = {f.name: f for f in ver_b.fields}
            all_names = sorted(set(a_fields) | set(b_fields))

            added = [n for n in all_names if n not in a_fields]
            removed = [n for n in all_names if n not in b_fields]
            changed = [
                n for n in all_names
                if n in a_fields and n in b_fields and a_fields[n] != b_fields[n]
            ]
            unchanged = [
                n for n in all_names
                if n in a_fields and n in b_fields and a_fields[n] == b_fields[n]
            ]

            if added:
                st.markdown(f"**➕ Added ({len(added)}):** {', '.join(f'`{n}`' for n in added)}")
            if removed:
                st.markdown(f"**➖ Removed ({len(removed)}):** {', '.join(f'`{n}`' for n in removed)}")
            if changed:
                st.markdown(f"**✏️ Changed ({len(changed)}):**")
                for n in changed:
                    fa, fb = a_fields[n], b_fields[n]
                    fa_lines = json.dumps(fa.model_dump(mode="json"), ensure_ascii=False, indent=2).splitlines(keepends=True)
                    fb_lines = json.dumps(fb.model_dump(mode="json"), ensure_ascii=False, indent=2).splitlines(keepends=True)
                    fdiff = list(difflib.unified_diff(fa_lines, fb_lines, fromfile=f"v{v_a}/{n}", tofile=f"v{v_b}/{n}"))
                    if fdiff:
                        st.code("".join(fdiff), language="diff")
            if not added and not removed and not changed:
                st.success(f"Fields are identical. ({len(unchanged)} unchanged)")

        # ── Per-version export ────────────────────────────────────────────────
        c_dl_a, c_dl_b = st.columns(2)
        for col, ver in [(c_dl_a, ver_a), (c_dl_b, ver_b)]:
            payload = {
                "config_name": ver.config_name,
                "version": ver.version,
                "provider": ver.provider.value,
                "prompt": ver.prompt,
                "fields": [f.model_dump(mode="json") for f in ver.fields],
                "provider_options": ver.provider_options,
            }
            col.download_button(
                f"⬇ Export v{ver.version}",
                data=json.dumps(payload, ensure_ascii=False, indent=2),
                file_name=f"{selected_name.lower().replace(' ', '_')}_v{ver.version}.json",
                mime="application/json",
                use_container_width=True,
                key=f"dl_{ver.version}",
            )


# ── Inspect a single version ──────────────────────────────────────────────────

st.divider()
st.subheader("Inspect version")

inspect_ver_num = st.selectbox("Version", options=ver_nums, index=0, key="inspect_v")
inspect_ver = next(v for v in versions if v.version == inspect_ver_num)

with st.expander("Prompt", expanded=False):
    st.code(inspect_ver.prompt, language="")

with st.expander(f"Fields ({len(inspect_ver.fields)})", expanded=True):
    field_rows = [
        {
            "name": f.name,
            "label": f.label,
            "type": f.type.value,
            "description": f.description,
            "example": f.example or "—",
        }
        for f in inspect_ver.fields
    ]
    st.dataframe(pd.DataFrame(field_rows), use_container_width=True, hide_index=True)


# ── Create new config from scratch ────────────────────────────────────────────

st.divider()
with st.expander("➕ Create new config from defaults"):
    new_name = st.text_input("Name", placeholder="e.g. Cyprus worksites", key="cfg_new_name")
    new_desc = st.text_input("Description (optional)", key="cfg_new_desc")
    new_provider = st.selectbox(
        "Starting provider",
        options=[p.value for p in ProviderName],
        format_func=lambda v: PROVIDER_LABELS.get(v, v),
        key="cfg_new_provider",
    )
    if st.button("Create", disabled=not new_name.strip(), key="cfg_create_btn"):
        from app.domain.defaults import DEFAULT_FIELDS, DEFAULT_PROMPT
        try:
            with session_scope() as s:
                ver = configs_repo.create_config(
                    s,
                    name=new_name.strip(),
                    description=new_desc.strip() or None,
                    prompt=DEFAULT_PROMPT,
                    fields=DEFAULT_FIELDS,
                    provider=ProviderName(new_provider),
                    provider_options={},
                    notes="Created from defaults.",
                    created_by=get_current_user(),
                )
            st.success(f"Created **{ver.config_name}** v1. Open the Playground to edit it.")
            st.rerun()
        except Exception as e:
            st.error(f"Failed: {e}")
