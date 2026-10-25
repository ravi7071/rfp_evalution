from __future__ import annotations

import json
from datetime import date
from typing import Any

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
from ingestion import extract_text_from_uploaded_file
from phase3_evaluation import evaluate_with_validation_gate
from phase4_scoring import rank_suppliers


def ensure_run_initialized() -> str:
    if "rfp_run_id" not in st.session_state:
        initialize_database()
        seed_evaluation_criteria()
        st.session_state.rfp_run_id = create_rfp_run(status="collecting_submissions")
    return st.session_state.rfp_run_id


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
    st.info(f"Current RFP Run ID: {rfp_run_id}")

    if "submissions" not in st.session_state:
        st.session_state.submissions = []

    if "evaluation_results" not in st.session_state:
        st.session_state.evaluation_results = []

    if "ranking_results" not in st.session_state:
        st.session_state.ranking_results = []

    if "run_export_payload" not in st.session_state:
        st.session_state.run_export_payload = {}

    if "selected_past_run_id" not in st.session_state:
        st.session_state.selected_past_run_id = ""

    if "past_ranking_results" not in st.session_state:
        st.session_state.past_ranking_results = []

    with st.sidebar:
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

    with st.form("supplier_submission_form"):
        supplier_name = st.text_input("Supplier Name")
        submission_date = st.date_input("Submission Date", value=date.today())
        experience_rating = st.slider("Experience Rating", min_value=1, max_value=10, value=5)
        uploaded_pdf = st.file_uploader("Upload Supplier PDF", type=["pdf"])
        submitted = st.form_submit_button("Extract and Save Draft")

    if submitted:
        if not supplier_name.strip():
            st.error("Supplier name is required.")
            return
        if uploaded_pdf is None:
            st.error("Please upload a PDF file.")
            return

        extracted_text = extract_text_from_uploaded_file(uploaded_pdf)
        print(f"\n--- Extracted text for supplier: {supplier_name} ---")
        print(extracted_text)
        print("--- End extracted text ---\n")

        st.session_state.submissions.append(
            {
                "supplier_name": supplier_name,
                "submission_date": submission_date.isoformat(),
                "experience_rating": experience_rating,
                "file_name": uploaded_pdf.name,
                "extracted_text": extracted_text,
                "text_length": len(extracted_text),
            }
        )

        st.success("Text extracted successfully. Printed full text to console.")
        st.text_area("Extracted Text Preview", value=extracted_text[:5000], height=280)

    st.subheader("Current Batch Submissions")
    if st.session_state.submissions:
        preview_rows = [
            {
                "supplier_name": item["supplier_name"],
                "submission_date": item["submission_date"],
                "experience_rating": item["experience_rating"],
                "file_name": item["file_name"],
                "text_length": item["text_length"],
            }
            for item in st.session_state.submissions
        ]
        st.dataframe(preview_rows, use_container_width=True)

        provider = st.selectbox(
            "LLM Provider",
            options=["openai", "gemini", "ollama"],
            index=0,
            help="Choose the provider for Phase 3 evaluation.",
        )

        default_models = {
            "openai": "gpt-4o-mini",
            "gemini": "gemini-2.0-flash",
            "ollama": "llama3.1",
        }
        model_name = st.text_input("Model Name", value=default_models[provider])

        api_key = ""
        if provider in {"openai", "gemini"}:
            api_key = st.text_input(label="Enter API Key", type="password")

        ollama_base_url = "http://localhost:11434"
        if provider == "ollama":
            ollama_base_url = st.text_input("Ollama Base URL", value="http://localhost:11434")

        if st.button("Run Evaluation", type="primary"):
            if provider in {"openai", "gemini"} and not api_key.strip():
                st.error(f"API key is required for provider '{provider}'.")
                return

            active_criteria = get_active_criteria()
            if not active_criteria:
                st.error("No active criteria found. Initialize and seed criteria first.")
                return

            batch_results = []
            with st.spinner("Running LLM evaluation and validation gate..."):
                for submission in st.session_state.submissions:
                    supplier_name = submission["supplier_name"]
                    extracted_text = submission.get("extracted_text", "")

                    try:
                        normalized_result = evaluate_with_validation_gate(
                            extracted_text=extracted_text,
                            active_criteria=active_criteria,
                            provider=provider,
                            model=model_name,
                            ollama_base_url=ollama_base_url,
                            api_key=api_key.strip() if provider in {"openai", "gemini"} else None,
                        )
                        batch_results.append(
                            {
                                "supplier_name": supplier_name,
                                "submission_date": submission["submission_date"],
                                "experience_rating": submission["experience_rating"],
                                "validated_json": normalized_result.model_dump(),
                            }
                        )
                    except Exception as error:
                        batch_results.append(
                            {
                                "supplier_name": supplier_name,
                                "error": str(error),
                            }
                        )

            st.session_state.evaluation_results = batch_results

            ranking_inputs = [
                {
                    "supplier_name": item["supplier_name"],
                    "submission_date": item["submission_date"],
                    "experience_rating": item["experience_rating"],
                    "evaluations": item["validated_json"]["evaluations"],
                }
                for item in batch_results
                if "validated_json" in item
            ]

            if ranking_inputs:
                st.session_state.ranking_results = rank_suppliers(
                    supplier_payloads=ranking_inputs,
                    active_criteria=active_criteria,
                )

                persisted_results = []
                validated_lookup = {
                    item["supplier_name"]: item["validated_json"]
                    for item in st.session_state.evaluation_results
                    if "validated_json" in item
                }
                delete_supplier_results_for_run(rfp_run_id=rfp_run_id)
                for ranked_item in st.session_state.ranking_results:
                    validated_json = validated_lookup.get(ranked_item["supplier_name"], {})
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
                    persisted_results.append({"id": record_id, **result_payload})

                update_rfp_run_status(rfp_run_id=rfp_run_id, status="completed")
                st.session_state.run_export_payload = build_run_export_payload(
                    rfp_run_id=rfp_run_id,
                    provider=provider,
                    model_name=model_name,
                    ranked_results=persisted_results,
                )
                st.success("Phase 5 complete: ranked batch saved to SQLite.")
            else:
                st.session_state.ranking_results = []
                st.session_state.run_export_payload = {}

        if st.session_state.evaluation_results:
            st.subheader("Phase 3 Validated Output")
            for result in st.session_state.evaluation_results:
                supplier_name = result["supplier_name"]
                if "error" in result:
                    st.error(f"{supplier_name}: {result['error']}")
                    continue
                st.markdown(f"**{supplier_name}**")
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
    else:
        st.write("No submissions yet.")

    if st.session_state.past_ranking_results:
        st.divider()
        st.header(f"Past Run Viewer: {st.session_state.selected_past_run_id}")
        render_leaderboard("Historical Leaderboard", st.session_state.past_ranking_results)
        render_detailed_scorecards(st.session_state.past_ranking_results)


if __name__ == "__main__":
    main()

