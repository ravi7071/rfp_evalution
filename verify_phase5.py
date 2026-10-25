from __future__ import annotations

import json

from database import (
    create_rfp_run,
    delete_supplier_results_for_run,
    get_connection,
    initialize_database,
    save_supplier_result,
    seed_evaluation_criteria,
    update_rfp_run_status,
)


def main() -> None:
    initialize_database()
    seed_evaluation_criteria()

    rfp_run_id = create_rfp_run(status="phase5_verification")
    delete_supplier_results_for_run(rfp_run_id)

    payload = {
        "phase3_validated_output": {
            "evaluations": [
                {
                    "criterion_id": 1,
                    "score": 8.0,
                    "max_score": 10,
                    "justification": "Good technical depth.",
                    "evidence": "Mentions scalability and recovery.",
                }
            ]
        },
        "phase4_scored_output": {
            "absolute_score": 0.8,
            "ppi": 92.0,
            "final_rank": 1,
        },
    }

    row_id = save_supplier_result(
        rfp_run_id=rfp_run_id,
        supplier_name="Supplier X",
        submission_date="2026-10-25",
        experience_rating=9,
        absolute_score=0.8,
        ppi=92.0,
        final_rank=1,
        result_payload=payload,
    )
    update_rfp_run_status(rfp_run_id=rfp_run_id, status="completed")

    with get_connection() as connection:
        cursor = connection.cursor()
        row = cursor.execute(
            """
            SELECT id, rfp_run_id, supplier_name, final_rank, result_json
            FROM supplier_results
            WHERE id = ?
            """,
            (row_id,),
        ).fetchone()

    assert row is not None
    stored_payload = json.loads(row["result_json"])
    assert stored_payload["phase3_validated_output"]["evaluations"][0]["criterion_id"] == 1
    assert row["final_rank"] == 1

    print("Phase 5 verification complete.")
    print(f"Saved supplier_result row id: {row_id}")


if __name__ == "__main__":
    main()

