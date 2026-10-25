from __future__ import annotations

import json

from database import get_active_criteria, initialize_database, seed_evaluation_criteria
from phase3_evaluation import evaluate_with_validation_gate


def mocked_llm_response(_: str) -> dict:
    return {
        "evaluations": [
            {
                "criterion_id": 1,
                "score": 18,
                "justification": "Strong architecture narrative and clear design.",
                "evidence": "Discusses modular components, failover, and scaling patterns.",
            },
            {
                "criterion_id": 2,
                "score": -2,
                "justification": "Timeline lacks explicit ownership milestones.",
                "evidence": "Mentions timeline but omits role mapping.",
            },
            {
                "criterion_id": 999,
                "score": 8,
                "justification": "Hallucinated criterion should be dropped.",
                "evidence": "No valid criterion mapping.",
            },
            {
                "criterion_id": 3,
                "score": 7,
                "justification": "",
                "evidence": "Invalid due to empty justification.",
            },
        ]
    }


def main() -> None:
    initialize_database()
    seed_evaluation_criteria()
    active_criteria = get_active_criteria()

    extracted_text = "Sample supplier proposal text for validation testing."
    normalized = evaluate_with_validation_gate(
        extracted_text=extracted_text,
        active_criteria=active_criteria,
        llm_callable=mocked_llm_response,
    )

    print("Phase 3 verification complete.")
    print(f"Dropped items: {normalized.dropped_items}")
    print(f"Clipped scores: {normalized.clipped_scores}")
    print(f"Backfilled items: {normalized.backfilled_items}")
    print(json.dumps(normalized.model_dump(), indent=2))


if __name__ == "__main__":
    main()

