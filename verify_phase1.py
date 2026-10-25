from __future__ import annotations

from pathlib import Path

from database import create_rfp_run, get_active_criteria, initialize_database, seed_evaluation_criteria


def main() -> None:
    db_path = Path("rfp_evaluation.db")

    initialize_database(db_path)
    seed_evaluation_criteria(db_path)

    criteria = get_active_criteria(db_path)
    assert len(criteria) == 5, f"Expected 5 active criteria, found {len(criteria)}"

    total_weight = sum(item["weight"] for item in criteria)
    assert abs(total_weight - 1.0) < 1e-9, f"Expected weight sum of 1.0, got {total_weight}"

    rfp_run_id = create_rfp_run(db_path)

    print("Phase 1 verification passed.")
    print(f"Active criteria count: {len(criteria)}")
    print(f"Active criteria weight sum: {total_weight:.2f}")
    print(f"Created rfp_run_id: {rfp_run_id}")


if __name__ == "__main__":
    main()

