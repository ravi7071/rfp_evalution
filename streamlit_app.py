from __future__ import annotations

import json
import hashlib
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import pandas as pd
import streamlit as st

from database import (
    create_rfp_run,
    delete_supplier_results_for_run,
    get_supplier_results_for_run,
    get_active_criteria,
    initialize_database,
    list_rfp_runs,
    save_supplier_result,
    seed_evaluation_criteria,
    update_rfp_run_status,
)
from ingestion import extract_text_from_pdf_bytes
from phase3_evaluation import evaluate_with_validation_gate
from phase4_scoring import rank_suppliers


def ensure_run_initialized() -> str:
    if "rfp_run_id" not in st.session_state:
        initialize_database()
        seed_evaluation_criteria()
        st.session_state.rfp_run_id = create_rfp_run(status="collecting_submissions")
    return st.session_state.rfp_run_id


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def default_provider_config() -> dict[str, str]:
    return {
        "provider": "openai",
        "model_name": "gpt-4o-mini",
        "api_key": "",
        "ollama_base_url": "http://localhost:11434",
    }


def default_batch_summary() -> dict[str, int]:
    return {
        "uploaded_total": 0,
        "metadata_valid": 0,
        "extracted_success": 0,
        "extracted_failed": 0,
        "evaluated_success": 0,
        "evaluated_failed": 0,
        "ranked_count": 0,
        "persisted_count": 0,
    }


def init_app_state(run_id: str) -> None:
    defaults: dict[str, Any] = {
        "rfp_run_id": run_id,
        "provider_config": default_provider_config(),
        "submissions": [],
        "evaluation_results": [],
        "ranking_results": [],
        "run_export_payload": {},
        "batch_summary": default_batch_summary(),
        "selected_past_run_id": "",
        "past_ranking_results": [],
        "last_state_init_at": _now_iso(),
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_current_run_state(new_run_id: str) -> None:
    st.session_state["rfp_run_id"] = new_run_id
    st.session_state["submissions"] = []
    st.session_state["evaluation_results"] = []
    st.session_state["ranking_results"] = []
    st.session_state["run_export_payload"] = {}
    st.session_state["batch_summary"] = default_batch_summary()


def build_run_export_payload(
    rfp_run_id: str,
    provider: str,
    model_name: str,
    ranked_results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "rfp_run_id": rfp_run_id,
        "provider": provider,
        "model": model_name,
        "supplier_count": len(ranked_results),
        "results": ranked_results,
    }


def build_submission_row(uploaded_file: Any, run_id: str) -> dict[str, Any]:
    file_bytes = uploaded_file.getvalue()
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    return {
        "submission_id": str(uuid4()),
        "rfp_run_id": run_id,
        "batch_index": 0,
        "file_name": uploaded_file.name,
        "file_type": Path(uploaded_file.name).suffix.lower(),
        "file_size_bytes": len(file_bytes),
        "file_size_kb": round(len(file_bytes) / 1024.0, 2),
        "file_hash": file_hash,
        "file_bytes": file_bytes,
        "supplier_name": Path(uploaded_file.name).stem,
        "submission_date": date.today().isoformat(),
        "experience_rating": 5,
        "metadata_status": "pending",
        "metadata_errors": [],
        "extract_status": "pending",
        "extract_started_at": None,
        "extract_completed_at": None,
        "extracted_text": "",
        "text_length": 0,
        "extract_error": None,
        "eval_status": "pending",
        "eval_started_at": None,
        "eval_completed_at": None,
        "validated_json": None,
        "gate_stats": {"dropped_items": 0, "clipped_scores": 0, "backfilled_items": 0},
        "eval_error": None,
        "score_status": "pending",
        "absolute_score": None,
        "ppi": None,
        "final_rank": None,
        "criterion_metrics": [],
        "persist_status": "pending",
        "persisted_row_id": None,
        "persist_error": None,
        "last_updated_at": _now_iso(),
    }


def validate_submission_metadata(submission: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not str(submission.get("supplier_name", "")).strip():
        errors.append("supplier_name is required")

    raw_date = str(submission.get("submission_date", "")).strip()
    try:
        date.fromisoformat(raw_date)
    except ValueError:
        errors.append("submission_date must be YYYY-MM-DD")

    experience = submission.get("experience_rating")
    if not isinstance(experience, int):
        errors.append("experience_rating must be an integer")
    elif experience < 1 or experience > 10:
        errors.append("experience_rating must be between 1 and 10")

    return errors


def refresh_batch_summary() -> None:
    submissions = st.session_state.submissions
    summary = default_batch_summary()
    summary["uploaded_total"] = len(submissions)
    summary["metadata_valid"] = len([s for s in submissions if s["metadata_status"] == "valid"])
    summary["extracted_success"] = len([s for s in submissions if s["extract_status"] == "success"])
    summary["extracted_failed"] = len([s for s in submissions if s["extract_status"] == "failed"])
    summary["evaluated_success"] = len([s for s in submissions if s["eval_status"] == "success"])
    summary["evaluated_failed"] = len([s for s in submissions if s["eval_status"] == "failed"])
    summary["ranked_count"] = len(st.session_state.ranking_results)
    summary["persisted_count"] = len([s for s in submissions if s["persist_status"] == "saved"])
    st.session_state.batch_summary = summary


def render_detailed_scorecards(ranked_results: list[dict[str, Any]]) -> None:
    st.subheader("Detailed Scorecards")
    for item in ranked_results:
        title = f"Rank #{item['final_rank']} - {item['supplier_name']}"
        with st.expander(title, expanded=False):
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Absolute Score", f"{item['absolute_score']:.4f}")
            col2.metric("PPI", f"{item['ppi']:.2f}")
            col3.metric("Submission Date", item["submission_date"])
            col4.metric("Experience", str(item["experience_rating"]))

            evaluations_by_id = {
                int(eval_item["criterion_id"]): eval_item for eval_item in item.get("evaluations", [])
            }
            detail_rows = []
            for metric in item.get("criterion_metrics", []):
                criterion_id = int(metric["criterion_id"])
                evaluation = evaluations_by_id.get(criterion_id, {})
                detail_rows.append(
                    {
                        "criterion_id": criterion_id,
                        "criterion_name": metric["criterion_name"],
                        "score": metric["score"],
                        "benchmark": metric["benchmark_score"],
                        "criterion_gap": metric["criterion_gap"],
                        "relative_%": round(metric["relative_performance_percent"], 2),
                        "justification": evaluation.get("justification", ""),
                        "evidence": evaluation.get("evidence", ""),
                    }
                )

            st.dataframe(detail_rows, use_container_width=True)


def render_leaderboard(title: str, ranked_results: list[dict[str, Any]]) -> None:
    st.subheader(title)
    leaderboard_rows = [
        {
            "final_rank": item["final_rank"],
            "supplier_name": item["supplier_name"],
            "ppi": round(item["ppi"], 2),
            "absolute_score": round(item["absolute_score"], 4),
            "submission_date": item["submission_date"],
            "experience_rating": item["experience_rating"],
        }
        for item in ranked_results
    ]
    st.dataframe(leaderboard_rows, use_container_width=True)


def reconstruct_ranked_results_from_saved_rows(saved_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    reconstructed: list[dict[str, Any]] = []
    for row in saved_rows:
        payload = json.loads(row["result_json"]) if row.get("result_json") else {}
        phase4 = payload.get("phase4_scored_output", {})
        reconstructed.append(
            {
                "supplier_name": row["supplier_name"],
                "submission_date": row["submission_date"],
                "experience_rating": int(row["experience_rating"]),
                "absolute_score": float(row["absolute_score"] or 0.0),
                "ppi": float(row["ppi"] or 0.0),
                "final_rank": int(row["final_rank"] or 0),
                "criterion_metrics": phase4.get("criterion_metrics", []),
                "evaluations": phase4.get("evaluations", []),
            }
        )

    reconstructed.sort(key=lambda item: (item["final_rank"], item["supplier_name"].lower()))
    return reconstructed


def main() -> None:
    st.set_page_config(page_title="RFP Evaluation Intake", layout="wide")
    st.title("RFP Evaluation - Phase 2/3 Intake")
    st.caption("Upload supplier PDFs, capture metadata, extract raw text, and run validated AI evaluation.")

    rfp_run_id = ensure_run_initialized()
    init_app_state(rfp_run_id)
    st.info(f"Current RFP Run ID: {rfp_run_id}")

    with st.sidebar:
        if st.button("Start New Run"):
            new_run_id = create_rfp_run(status="collecting_submissions")
            reset_current_run_state(new_run_id)
            st.rerun()

        st.header("Past Runs")
        run_rows = list_rfp_runs()
        if run_rows:
            run_labels = [
                (
                    row["rfp_run_id"],
                    f"{row['rfp_run_id']} | {row['status']} | suppliers={row['supplier_count']}"
                )
                for row in run_rows
            ]
            selected_label = st.selectbox(
                "Select RFP_RUN_ID",
                options=[label for _, label in run_labels],
            )
            selected_run_id = next(run_id for run_id, label in run_labels if label == selected_label)

            if st.button("Load Past Run"):
                saved_rows = get_supplier_results_for_run(selected_run_id)
                st.session_state.selected_past_run_id = selected_run_id
                st.session_state.past_ranking_results = reconstruct_ranked_results_from_saved_rows(saved_rows)
                if not saved_rows:
                    st.sidebar.warning("No supplier_results rows found for the selected run.")
        else:
            st.caption("No historical runs found yet.")

    st.subheader("Step 1: Upload PDFs")
    uploaded_files = st.file_uploader(
        "Upload Supplier PDFs",
        type=["pdf"],
        accept_multiple_files=True,
    )

    add_col, clear_col = st.columns([1, 1])
    with add_col:
        if st.button("Add to Batch"):
            if not uploaded_files:
                st.warning("Please choose one or more PDF files first.")
            else:
                existing_hashes = {item["file_hash"] for item in st.session_state.submissions}
                added_count = 0
                skipped_count = 0
                for uploaded in uploaded_files:
                    row = build_submission_row(uploaded, st.session_state.rfp_run_id)
                    if row["file_hash"] in existing_hashes:
                        skipped_count += 1
                        continue
                    row["batch_index"] = len(st.session_state.submissions) + 1
                    st.session_state.submissions.append(row)
                    existing_hashes.add(row["file_hash"])
                    added_count += 1
                refresh_batch_summary()
                st.success(f"Added {added_count} file(s) to batch. Skipped duplicates: {skipped_count}.")

    with clear_col:
        if st.button("Clear Staged Files"):
            st.session_state.submissions = []
            st.session_state.evaluation_results = []
            st.session_state.ranking_results = []
            st.session_state.run_export_payload = {}
            refresh_batch_summary()
            st.info("Cleared staged batch.")

    if not st.session_state.submissions:
        st.write("No submissions yet.")
    else:
        st.subheader("Step 2: Staged Metadata Table")
        metadata_rows = [
            {
                "submission_id": item["submission_id"],
                "file_name": item["file_name"],
                "supplier_name": item["supplier_name"],
                "submission_date": date.fromisoformat(item["submission_date"]),
                "experience_rating": item["experience_rating"],
                "metadata_status": item["metadata_status"],
            }
            for item in st.session_state.submissions
        ]

        edited_df = st.data_editor(
            pd.DataFrame(metadata_rows),
            use_container_width=True,
            num_rows="fixed",
            column_config={
                "submission_id": st.column_config.TextColumn("Submission ID", disabled=True),
                "file_name": st.column_config.TextColumn("File Name", disabled=True),
                "supplier_name": st.column_config.TextColumn("Supplier Name", required=True),
                "submission_date": st.column_config.DateColumn("Submission Date"),
                "experience_rating": st.column_config.NumberColumn("Experience Rating", min_value=1, max_value=10, step=1),
                "metadata_status": st.column_config.TextColumn("Metadata Status", disabled=True),
            },
            hide_index=True,
            key="staged_metadata_editor",
        )

        if st.button("Apply Metadata & Validate"):
            edited_records = edited_df.to_dict("records")
            by_id = {row["submission_id"]: row for row in edited_records}
            for item in st.session_state.submissions:
                edit = by_id.get(item["submission_id"])
                if edit is None:
                    continue
                submission_date_value = edit["submission_date"]
                if hasattr(submission_date_value, "isoformat"):
                    if hasattr(submission_date_value, "date"):
                        submission_date_text = submission_date_value.date().isoformat()
                    else:
                        submission_date_text = submission_date_value.isoformat()
                else:
                    submission_date_text = str(submission_date_value)

                item["supplier_name"] = str(edit["supplier_name"]).strip()
                item["submission_date"] = submission_date_text
                item["experience_rating"] = int(edit["experience_rating"])
                metadata_errors = validate_submission_metadata(item)
                item["metadata_errors"] = metadata_errors
                item["metadata_status"] = "valid" if not metadata_errors else "invalid"
                item["last_updated_at"] = _now_iso()

            refresh_batch_summary()
            st.success("Metadata applied and validated.")

        invalid_rows = [item for item in st.session_state.submissions if item["metadata_status"] == "invalid"]
        if invalid_rows:
            st.warning("Some rows have invalid metadata:")
            for item in invalid_rows:
                st.write(f"- `{item['file_name']}`: {', '.join(item['metadata_errors'])}")

        st.subheader("Step 3: Extract Text")
        extract_col1, extract_col2 = st.columns([1, 1])
        run_extraction = extract_col1.button("Run Extraction")
        retry_extraction = extract_col2.button("Retry Failed Extraction")

        if run_extraction or retry_extraction:
            targets = [
                item
                for item in st.session_state.submissions
                if item["metadata_status"] == "valid"
                and (item["extract_status"] in {"pending", "failed"} if run_extraction else item["extract_status"] == "failed")
            ]
            if not targets:
                st.info("No eligible rows for extraction.")
            else:
                progress = st.progress(0.0)
                for index, item in enumerate(targets, start=1):
                    item["extract_status"] = "running"
                    item["extract_started_at"] = _now_iso()
                    try:
                        extracted_text = extract_text_from_pdf_bytes(item["file_bytes"])
                        item["extracted_text"] = extracted_text
                        item["text_length"] = len(extracted_text)
                        item["extract_status"] = "success"
                        item["extract_error"] = None
                    except Exception as error:
                        item["extract_status"] = "failed"
                        item["extract_error"] = str(error)
                    item["extract_completed_at"] = _now_iso()
                    item["last_updated_at"] = _now_iso()
                    progress.progress(index / len(targets))

                refresh_batch_summary()
                st.success("Extraction step completed.")

        st.subheader("Current Batch Submissions")
        st.dataframe(
            [
                {
                    "file_name": item["file_name"],
                    "supplier_name": item["supplier_name"],
                    "submission_date": item["submission_date"],
                    "experience_rating": item["experience_rating"],
                    "metadata_status": item["metadata_status"],
                    "extract_status": item["extract_status"],
                    "text_length": item["text_length"],
                    "eval_status": item["eval_status"],
                    "persist_status": item["persist_status"],
                }
                for item in st.session_state.submissions
            ],
            use_container_width=True,
        )

        st.subheader("Step 4: Evaluation Gate")
        provider_options = ["openai", "gemini", "ollama"]
        provider_config: dict[str, str] = st.session_state.provider_config
        default_provider = provider_config.get("provider", "openai")
        provider_index = provider_options.index(default_provider) if default_provider in provider_options else 0

        provider = st.selectbox("LLM Provider", options=provider_options, index=provider_index)

        default_models = {
            "openai": "gpt-4o-mini",
            "gemini": "gemini-2.0-flash",
            "ollama": "llama3.1",
        }
        default_model_name = provider_config.get("model_name", default_models[provider])
        model_name = st.text_input("Model Name", value=default_model_name)

        api_key = provider_config.get("api_key", "")
        if provider in {"openai", "gemini"}:
            api_key = st.text_input(label="Enter API Key", value=api_key, type="password")

        ollama_base_url = provider_config.get("ollama_base_url", "http://localhost:11434")
        if provider == "ollama":
            ollama_base_url = st.text_input("Ollama Base URL", value=ollama_base_url)

        st.session_state.provider_config = {
            "provider": provider,
            "model_name": model_name,
            "api_key": api_key if provider in {"openai", "gemini"} else "",
            "ollama_base_url": ollama_base_url,
        }

        run_eval_col, retry_eval_col = st.columns([1, 1])
        run_evaluation = run_eval_col.button("Run Evaluation", type="primary")
        retry_failed_eval = retry_eval_col.button("Retry Failed Evaluation")

        if run_evaluation or retry_failed_eval:
            if provider in {"openai", "gemini"} and not api_key.strip():
                st.error(f"API key is required for provider '{provider}'.")
            else:
                active_criteria = get_active_criteria()
                if not active_criteria:
                    st.error("No active criteria found. Initialize and seed criteria first.")
                else:
                    targets = [
                        item
                        for item in st.session_state.submissions
                        if item["extract_status"] == "success"
                        and (item["eval_status"] in {"pending", "failed"} if run_evaluation else item["eval_status"] == "failed")
                    ]

                    if not targets:
                        st.info("No eligible rows for evaluation.")
                    else:
                        progress = st.progress(0.0)
                        for index, item in enumerate(targets, start=1):
                            item["eval_status"] = "running"
                            item["eval_started_at"] = _now_iso()
                            try:
                                normalized_result = evaluate_with_validation_gate(
                                    extracted_text=item["extracted_text"],
                                    active_criteria=active_criteria,
                                    provider=provider,
                                    model=model_name,
                                    ollama_base_url=ollama_base_url,
                                    api_key=api_key.strip() if provider in {"openai", "gemini"} else None,
                                )
                                item["validated_json"] = normalized_result.model_dump()
                                item["gate_stats"] = {
                                    "dropped_items": normalized_result.dropped_items,
                                    "clipped_scores": normalized_result.clipped_scores,
                                    "backfilled_items": normalized_result.backfilled_items,
                                }
                                item["eval_status"] = "success"
                                item["eval_error"] = None
                            except Exception as error:
                                item["eval_status"] = "failed"
                                item["eval_error"] = str(error)
                            item["eval_completed_at"] = _now_iso()
                            item["last_updated_at"] = _now_iso()
                            progress.progress(index / len(targets))

                        st.session_state.evaluation_results = [
                            {
                                "submission_id": item["submission_id"],
                                "supplier_name": item["supplier_name"],
                                "eval_status": item["eval_status"],
                                "validated_json": item["validated_json"],
                                "error": item["eval_error"],
                            }
                            for item in st.session_state.submissions
                            if item["eval_status"] in {"success", "failed"}
                        ]
                        refresh_batch_summary()
                        st.success("Evaluation step completed.")

        st.subheader("Step 5: Score, Rank, Save")
        if st.button("Compute Rankings & Save"):
            active_criteria = get_active_criteria()
            ranking_inputs = [
                {
                    "supplier_name": item["supplier_name"],
                    "submission_date": item["submission_date"],
                    "experience_rating": item["experience_rating"],
                    "evaluations": item["validated_json"]["evaluations"],
                }
                for item in st.session_state.submissions
                if item["eval_status"] == "success" and item.get("validated_json")
            ]

            if not ranking_inputs:
                st.warning("No successfully evaluated submissions available for ranking.")
            else:
                st.session_state.ranking_results = rank_suppliers(
                    supplier_payloads=ranking_inputs,
                    active_criteria=active_criteria,
                )

                persisted_results = []
                validated_lookup = {
                    (item["supplier_name"], item["submission_date"], item["experience_rating"]): item
                    for item in st.session_state.submissions
                    if item["eval_status"] == "success"
                }

                delete_supplier_results_for_run(rfp_run_id=rfp_run_id)
                for ranked_item in st.session_state.ranking_results:
                    lookup_key = (
                        ranked_item["supplier_name"],
                        ranked_item["submission_date"],
                        ranked_item["experience_rating"],
                    )
                    source_submission = validated_lookup.get(lookup_key)
                    validated_json = source_submission.get("validated_json", {}) if source_submission else {}
                    result_payload = {
                        "supplier_name": ranked_item["supplier_name"],
                        "submission_date": ranked_item["submission_date"],
                        "experience_rating": ranked_item["experience_rating"],
                        "absolute_score": ranked_item["absolute_score"],
                        "ppi": ranked_item["ppi"],
                        "final_rank": ranked_item["final_rank"],
                        "criterion_metrics": ranked_item["criterion_metrics"],
                        "phase3_validated_output": validated_json,
                        "phase4_scored_output": {
                            "evaluations": ranked_item["evaluations"],
                            "criterion_metrics": ranked_item["criterion_metrics"],
                        },
                    }
                    record_id = save_supplier_result(
                        rfp_run_id=rfp_run_id,
                        supplier_name=ranked_item["supplier_name"],
                        submission_date=ranked_item["submission_date"],
                        experience_rating=ranked_item["experience_rating"],
                        absolute_score=ranked_item["absolute_score"],
                        ppi=ranked_item["ppi"],
                        final_rank=ranked_item["final_rank"],
                        result_payload=result_payload,
                    )
                    if source_submission is not None:
                        source_submission["score_status"] = "success"
                        source_submission["absolute_score"] = ranked_item["absolute_score"]
                        source_submission["ppi"] = ranked_item["ppi"]
                        source_submission["final_rank"] = ranked_item["final_rank"]
                        source_submission["criterion_metrics"] = ranked_item["criterion_metrics"]
                        source_submission["persist_status"] = "saved"
                        source_submission["persisted_row_id"] = record_id
                        source_submission["persist_error"] = None

                    persisted_results.append({"id": record_id, **result_payload})

                update_rfp_run_status(rfp_run_id=rfp_run_id, status="completed")
                st.session_state.run_export_payload = build_run_export_payload(
                    rfp_run_id=rfp_run_id,
                    provider=provider,
                    model_name=model_name,
                    ranked_results=persisted_results,
                )
                refresh_batch_summary()
                st.success("Phase 5 complete: ranked batch saved to SQLite.")

        st.subheader("Batch Summary")
        summary = st.session_state.batch_summary
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Uploaded", summary["uploaded_total"])
        c2.metric("Metadata Valid", summary["metadata_valid"])
        c3.metric("Extraction OK", summary["extracted_success"])
        c4.metric("Evaluation OK", summary["evaluated_success"])

        if st.session_state.evaluation_results:
            st.subheader("Phase 3 Validated Output")
            for result in st.session_state.evaluation_results:
                if result["eval_status"] == "failed":
                    st.error(f"{result['supplier_name']}: {result['error']}")
                    continue
                st.markdown(f"**{result['supplier_name']}**")
                st.json(result["validated_json"])

        if st.session_state.ranking_results:
            render_leaderboard("Final Leaderboard", st.session_state.ranking_results)
            render_detailed_scorecards(st.session_state.ranking_results)

            if st.session_state.run_export_payload:
                st.download_button(
                    label="Download JSON",
                    data=json.dumps(st.session_state.run_export_payload, indent=2),
                    file_name=f"rfp_run_{rfp_run_id}_results.json",
                    mime="application/json",
                )

    if st.session_state.past_ranking_results:
        st.divider()
        st.header(f"Past Run Viewer: {st.session_state.selected_past_run_id}")
        render_leaderboard("Historical Leaderboard", st.session_state.past_ranking_results)
        render_detailed_scorecards(st.session_state.past_ranking_results)


if __name__ == "__main__":
    main()

