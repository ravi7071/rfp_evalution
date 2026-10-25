from __future__ import annotations

import json
from math import isclose

from database import get_active_criteria, initialize_database, seed_evaluation_criteria
from phase4_scoring import rank_suppliers


def main() -> None:
    initialize_database()
    seed_evaluation_criteria()
    active_criteria = get_active_criteria()

    supplier_payloads = [
        {
            "supplier_name": "Alpha Systems",
            "submission_date": "2026-10-20",
            "experience_rating": 8,
            "evaluations": [
                {"criterion_id": 1, "score": 8},
                {"criterion_id": 2, "score": 7},
                {"criterion_id": 3, "score": 9},
                {"criterion_id": 4, "score": 8},
                {"criterion_id": 5, "score": 8},
            ],
        },
        {
            "supplier_name": "Beta Tech",
            "submission_date": "2026-10-19",
            "experience_rating": 7,
            "evaluations": [
                {"criterion_id": 1, "score": 9},
                {"criterion_id": 2, "score": 8},
                {"criterion_id": 3, "score": 7},
                {"criterion_id": 4, "score": 7},
                {"criterion_id": 5, "score": 9},
            ],
        },
        {
            "supplier_name": "Gamma Works",
            "submission_date": "2026-10-19",
            "experience_rating": 9,
            "evaluations": [
                {"criterion_id": 1, "score": 9},
                {"criterion_id": 2, "score": 8},
                {"criterion_id": 3, "score": 7},
                {"criterion_id": 4, "score": 7},
                {"criterion_id": 5, "score": 9},
            ],
        },
    ]

    ranked = rank_suppliers(supplier_payloads=supplier_payloads, active_criteria=active_criteria)

    ranked_names = [item["supplier_name"] for item in ranked]
    expected_order = ["Gamma Works", "Beta Tech", "Alpha Systems"]
    assert ranked_names == expected_order, f"Unexpected rank order: {ranked_names}"

    rank_sequence = [item["final_rank"] for item in ranked]
    assert rank_sequence == [1, 2, 3], f"Unexpected rank sequence: {rank_sequence}"

    gamma = ranked[0]
    beta = ranked[1]
    alpha = ranked[2]

    assert isclose(gamma["absolute_score"], 0.805, rel_tol=1e-9)
    assert isclose(beta["absolute_score"], 0.805, rel_tol=1e-9)
    assert isclose(alpha["absolute_score"], 0.795, rel_tol=1e-9)

    assert isclose(gamma["ppi"], beta["ppi"], rel_tol=1e-12)
    assert gamma["submission_date"] == beta["submission_date"]
    assert gamma["experience_rating"] > beta["experience_rating"]

    gamma_metrics = {item["criterion_id"]: item for item in gamma["criterion_metrics"]}
    assert gamma_metrics[1]["benchmark_score"] == 9.0
    assert gamma_metrics[2]["benchmark_score"] == 8.0
    assert gamma_metrics[3]["benchmark_score"] == 9.0
    assert gamma_metrics[4]["benchmark_score"] == 8.0
    assert gamma_metrics[5]["benchmark_score"] == 9.0
    assert gamma_metrics[3]["criterion_gap"] == 2.0
    assert isclose(gamma_metrics[3]["relative_performance_percent"], 77.77777777777779, rel_tol=1e-12)

    print("Phase 4 verification complete.")
    print("Assertions passed for formulas and tie-break ranking.")
    print(json.dumps(ranked, indent=2))


if __name__ == "__main__":
    main()

