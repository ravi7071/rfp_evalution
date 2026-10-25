from __future__ import annotations

import json

from database import get_supplier_results_for_run, list_rfp_runs


def main() -> None:
    runs = list_rfp_runs()
    assert isinstance(runs, list)

    if not runs:
        print("No runs available yet. Past Runs verifier skipped.")
        return

    run_id = runs[0]["rfp_run_id"]
    rows = get_supplier_results_for_run(run_id)
    if rows:
        parsed_payload = json.loads(rows[0]["result_json"]) if rows[0].get("result_json") else {}
        assert isinstance(parsed_payload, dict)
        assert "phase4_scored_output" in parsed_payload

    print(f"Past Runs verifier complete for run: {run_id}")
    print(f"Rows loaded: {len(rows)}")


if __name__ == "__main__":
    main()

