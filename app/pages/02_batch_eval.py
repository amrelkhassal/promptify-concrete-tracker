from __future__ import annotations

import threading
from datetime import datetime, timezone
from uuid import UUID

import pandas as pd
import streamlit as st
from sqlalchemy import select

from app.core.auth import get_current_user
from app.repos import configs as configs_repo
from app.repos import datasets as datasets_repo
from app.repos.db import (
    ConfigVersion,
    Evaluation,
    session_scope,
)
from app.services import eval as eval_svc

st.set_page_config(page_title="Batch Eval · Promptify", layout="wide")
st.title("Batch Evaluation")
st.caption("Run a saved config against a labelled dataset and measure per-field accuracy.")

# ── Load data ─────────────────────────────────────────────────────────────────

with session_scope() as s:
    all_configs = configs_repo.list_configs(s)
    all_datasets = datasets_repo.list_datasets(s)

if not all_configs:
    st.warning("No configs found. Create one on the **Configs** page first.")
    st.stop()

if not all_datasets:
    st.warning("No datasets found. Upload one on the **Datasets** page first.")
    st.stop()

# ── Evaluation setup ──────────────────────────────────────────────────────────

st.subheader("New evaluation")

# Build version list: "Config vN — provider"
version_options: list[tuple[str, UUID]] = []
with session_scope() as s:
    for cfg_row in all_configs:
        cfg = cfg_row["config"]
        versions = configs_repo.list_versions(s, cfg.id)
        for v in versions:
            label = f"{cfg.name}  v{v.version}  —  {v.provider}"
            version_options.append((label, v.id))

version_labels = [label for label, _ in version_options]
selected_version_label = st.selectbox("Config version", version_labels)
selected_version_id = next(
    vid for label, vid in version_options if label == selected_version_label
)

dataset_names = [d["dataset"].name for d in all_datasets]
selected_dataset_name = st.selectbox("Dataset", dataset_names)
selected_dataset = next(
    d["dataset"] for d in all_datasets if d["dataset"].name == selected_dataset_name
)

col_run, col_skip = st.columns([2, 3])
with col_run:
    run_btn = st.button("▶ Run evaluation", type="primary")

# ── Run evaluation ────────────────────────────────────────────────────────────

if run_btn:
    with session_scope() as s:
        # Create evaluation record
        eval_obj = Evaluation(
            config_version_id=selected_version_id,
            dataset_id=selected_dataset.id,
            status="running",
            created_by=get_current_user(),
            created_at=datetime.now(timezone.utc),
        )
        s.add(eval_obj)
        s.flush()
        eval_id: UUID = eval_obj.id

    progress_bar = st.progress(0, text="Starting…")
    status_text = st.empty()

    def _on_progress(current: int, total: int, doc_key: str) -> None:
        if total > 0:
            progress_bar.progress(current / total, text=f"Processing {doc_key}…")
        status_text.text(f"{current}/{total} documents")

    try:
        eval_svc.run_evaluation(eval_id, on_progress=_on_progress)
        progress_bar.progress(1.0, text="Done ✓")
        status_text.empty()
        st.success("Evaluation complete!")
        st.rerun()
    except Exception as e:
        st.exception(e)

st.divider()

# ── Evaluation history ────────────────────────────────────────────────────────

st.subheader("Evaluation history")

with session_scope() as s:
    evals_raw = s.execute(
        select(Evaluation)
        .where(Evaluation.dataset_id == selected_dataset.id)
        .order_by(Evaluation.created_at.desc())
    ).scalars().all()

    # Detach from session by converting to plain dicts
    evals = [
        {
            "id": e.id,
            "config_version_id": e.config_version_id,
            "status": e.status,
            "overall_accuracy": (e.summary or {}).get("overall_accuracy"),
            "doc_count": (e.summary or {}).get("doc_count"),
            "created_by": e.created_by,
            "created_at": e.created_at,
            "finished_at": e.finished_at,
        }
        for e in evals_raw
    ]

    # Resolve version labels for display
    version_label_map: dict[UUID, str] = {}
    for label, vid in version_options:
        version_label_map[vid] = label

if not evals:
    st.info("No evaluations yet for this dataset.")
    st.stop()

history_rows = [
    {
        "Config version": version_label_map.get(e["config_version_id"], str(e["config_version_id"])),
        "Status": e["status"],
        "Accuracy %": f"{e['overall_accuracy']}%" if e["overall_accuracy"] is not None else "—",
        "Docs": e["doc_count"] or "—",
        "Run by": e["created_by"],
        "Started": e["created_at"].strftime("%Y-%m-%d %H:%M") if e["created_at"] else "—",
    }
    for e in evals
]
st.dataframe(pd.DataFrame(history_rows), use_container_width=True, hide_index=True)

# ── Inspect an evaluation ─────────────────────────────────────────────────────

eval_labels = [
    f"{version_label_map.get(e['config_version_id'], '?')}  —  {e['created_at'].strftime('%Y-%m-%d %H:%M') if e['created_at'] else '?'}"
    for e in evals
    if e["status"] == "done"
]

if not eval_labels:
    st.info("Run an evaluation above to see results.")
    st.stop()

selected_eval_label = st.selectbox("Inspect evaluation", eval_labels)
selected_eval = next(
    e
    for e in evals
    if e["status"] == "done"
    and f"{version_label_map.get(e['config_version_id'], '?')}  —  {e['created_at'].strftime('%Y-%m-%d %H:%M') if e['created_at'] else '?'}"
    == selected_eval_label
)

with session_scope() as s:
    eval_obj_full = s.get(Evaluation, selected_eval["id"])
    summary = eval_obj_full.summary or {}
    per_field = summary.get("per_field", {})
    per_worksite = summary.get("per_worksite", {})
    overall = summary.get("overall_accuracy")
    doc_count = summary.get("doc_count", 0)
    detail = eval_svc.get_evaluation_detail(s, selected_eval["id"])
    excel_bytes = eval_svc.export_excel(s, selected_eval["id"])

# ── Overall accuracy banner ───────────────────────────────────────────────────

acc_color = (
    "🟢" if overall is not None and overall >= 85
    else "🟡" if overall is not None and overall >= 60
    else "🔴"
)
st.metric(
    label=f"{acc_color} Overall accuracy",
    value=f"{overall}%" if overall is not None else "—",
    help=f"Across {doc_count} documents, all fields, ignoring GT_EMPTY cells.",
)

st.download_button(
    "⬇ Download Excel report",
    data=excel_bytes,
    file_name=f"eval_{selected_eval['id']}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
)

st.divider()

# ── Per-field accuracy table ──────────────────────────────────────────────────

if per_field:
    st.subheader("Per-field accuracy")
    field_rows = []
    for fn, fd in per_field.items():
        pct = fd.get("accuracy")
        field_rows.append(
            {
                "Field": fn,
                "Accuracy %": f"{pct}%" if pct is not None else "—",
                "MATCH": fd.get("MATCH", 0),
                "MISMATCH": fd.get("MISMATCH", 0),
                "MISSING": fd.get("MISSING", 0),
                "GT_EMPTY": fd.get("GT_EMPTY", 0),
            }
        )
    st.dataframe(pd.DataFrame(field_rows), use_container_width=True, hide_index=True)

# ── Per-worksite accuracy table ───────────────────────────────────────────────

if per_worksite:
    st.subheader("Per-worksite accuracy")
    ws_rows = [
        {
            "Worksite": ws_name,
            "Accuracy %": f"{wd.get('accuracy')}%" if wd.get("accuracy") is not None else "—",
            "Evaluated fields": wd.get("count", 0),
        }
        for ws_name, wd in sorted(per_worksite.items())
    ]
    st.dataframe(pd.DataFrame(ws_rows), use_container_width=True, hide_index=True)

st.divider()

# ── Compare two evaluations ───────────────────────────────────────────────────

done_evals = [e for e in evals if e["status"] == "done"]
if len(done_evals) >= 2:
    with st.expander("📊 Compare two evaluations"):
        compare_labels = [
            f"{version_label_map.get(e['config_version_id'], '?')}  —  {e['created_at'].strftime('%Y-%m-%d %H:%M') if e['created_at'] else '?'}"
            for e in done_evals
        ]
        col_a, col_b = st.columns(2)
        with col_a:
            label_a = st.selectbox("Evaluation A", compare_labels, key="cmp_a")
        with col_b:
            label_b = st.selectbox(
                "Evaluation B",
                compare_labels,
                index=min(1, len(compare_labels) - 1),
                key="cmp_b",
            )

        if label_a != label_b:
            eval_a = next(
                e
                for e in done_evals
                if f"{version_label_map.get(e['config_version_id'], '?')}  —  {e['created_at'].strftime('%Y-%m-%d %H:%M') if e['created_at'] else '?'}"
                == label_a
            )
            eval_b = next(
                e
                for e in done_evals
                if f"{version_label_map.get(e['config_version_id'], '?')}  —  {e['created_at'].strftime('%Y-%m-%d %H:%M') if e['created_at'] else '?'}"
                == label_b
            )

            pf_a = (eval_a.get("summary") or {}).get("per_field", {})
            pf_b = (eval_b.get("summary") or {}).get("per_field", {})

            # Re-fetch summaries
            with session_scope() as s:
                obj_a = s.get(Evaluation, eval_a["id"])
                obj_b = s.get(Evaluation, eval_b["id"])
                pf_a = (obj_a.summary or {}).get("per_field", {})
                pf_b = (obj_b.summary or {}).get("per_field", {})

            all_fields = sorted(set(list(pf_a.keys()) + list(pf_b.keys())))
            delta_rows = []
            for fn in all_fields:
                acc_a = (pf_a.get(fn) or {}).get("accuracy")
                acc_b = (pf_b.get(fn) or {}).get("accuracy")
                if acc_a is not None and acc_b is not None:
                    delta = round(acc_b - acc_a, 1)
                    delta_str = f"+{delta}%" if delta > 0 else f"{delta}%"
                else:
                    delta_str = "—"
                delta_rows.append(
                    {
                        "Field": fn,
                        f"A: {label_a[:30]}…": f"{acc_a}%" if acc_a is not None else "—",
                        f"B: {label_b[:30]}…": f"{acc_b}%" if acc_b is not None else "—",
                        "Δ (B − A)": delta_str,
                    }
                )
            st.dataframe(pd.DataFrame(delta_rows), use_container_width=True, hide_index=True)
        else:
            st.info("Select two different evaluations to compare.")

st.divider()

# ── Document-level drill-down ─────────────────────────────────────────────────

with st.expander("🔍 Document-level detail"):
    if not detail:
        st.info("No detail rows.")
    else:
        STATUS_COLOR = {
            "MATCH": "🟢",
            "MISMATCH": "🔴",
            "MISSING": "🟡",
            "GT_EMPTY": "⬜",
        }

        doc_keys = [d["doc_key"] for d in detail]
        selected_doc_key = st.selectbox("Document", doc_keys)
        doc = next(d for d in detail if d["doc_key"] == selected_doc_key)

        st.caption(
            f"Worksite: **{doc.get('worksite') or '—'}**  |  "
            f"Latency: **{doc.get('latency_ms') or '—'} ms**"
        )
        if doc.get("error"):
            st.error(f"Error: {doc['error']}")

        gt = doc["ground_truth"]
        extraction = doc["extraction"]
        statuses = doc["field_statuses"]

        field_detail_rows = []
        for fn in sorted(set(list(gt.keys()) + list(extraction.keys()))):
            status = statuses.get(fn, "MISSING")
            icon = STATUS_COLOR.get(status, "❓")
            field_detail_rows.append(
                {
                    "Field": fn,
                    "Status": f"{icon} {status}",
                    "Ground truth": gt.get(fn) if gt.get(fn) is not None else "—",
                    "Extracted": extraction.get(fn) if extraction.get(fn) is not None else "—",
                }
            )
        st.dataframe(
            pd.DataFrame(field_detail_rows), use_container_width=True, hide_index=True
        )
