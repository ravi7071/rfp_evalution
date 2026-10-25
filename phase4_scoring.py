from __future__ import annotations

from datetime import date
from typing import Any


def calculate_absolute_weighted_score(
    evaluations: list[dict[str, Any]],
    active_criteria: list[dict[str, Any]],
) -> float:
    evaluations_by_id = {int(item["criterion_id"]): float(item["score"]) for item in evaluations}
    total = 0.0
    for criterion in active_criteria:
        criterion_id = int(criterion["criterion_id"])
        max_score = float(criterion["max_score"])
        weight = float(criterion["weight"])
        raw_score = evaluations_by_id.get(criterion_id, 0.0)
        normalized = (raw_score / max_score) if max_score > 0 else 0.0
        total += normalized * weight
    return total


def calculate_criterion_benchmarks(
    all_supplier_evaluations: list[list[dict[str, Any]]],
    active_criteria: list[dict[str, Any]],
) -> dict[int, float]:
    benchmarks = {int(item["criterion_id"]): 0.0 for item in active_criteria}
    for supplier_evaluations in all_supplier_evaluations:
        for criterion_eval in supplier_evaluations:
            criterion_id = int(criterion_eval["criterion_id"])
            score = float(criterion_eval["score"])
            if criterion_id in benchmarks:
                benchmarks[criterion_id] = max(benchmarks[criterion_id], score)
    return benchmarks


def calculate_criterion_gap(score: float, benchmark_score: float) -> float:
    return benchmark_score - score


def calculate_relative_performance_percent(score: float, benchmark_score: float) -> float:
    if benchmark_score <= 0:
        return 0.0
    return (score / benchmark_score) * 100.0


def calculate_ppi(
    evaluations: list[dict[str, Any]],
    active_criteria: list[dict[str, Any]],
    criterion_benchmarks: dict[int, float],
) -> float:
    evaluations_by_id = {int(item["criterion_id"]): float(item["score"]) for item in evaluations}
    weighted_total = 0.0

    for criterion in active_criteria:
        criterion_id = int(criterion["criterion_id"])
        weight = float(criterion["weight"])
        supplier_score = evaluations_by_id.get(criterion_id, 0.0)
        benchmark_score = float(criterion_benchmarks.get(criterion_id, 0.0))
        relative_percent = calculate_relative_performance_percent(supplier_score, benchmark_score)
        weighted_total += relative_percent * weight

    return weighted_total


def build_criterion_metrics(
    evaluations: list[dict[str, Any]],
    active_criteria: list[dict[str, Any]],
    criterion_benchmarks: dict[int, float],
) -> list[dict[str, Any]]:
    evaluations_by_id = {int(item["criterion_id"]): item for item in evaluations}
    metrics: list[dict[str, Any]] = []

    for criterion in active_criteria:
        criterion_id = int(criterion["criterion_id"])
        score = float(evaluations_by_id.get(criterion_id, {}).get("score", 0.0))
        benchmark = float(criterion_benchmarks.get(criterion_id, 0.0))
        criterion_gap = calculate_criterion_gap(score, benchmark)
        relative_percent = calculate_relative_performance_percent(score, benchmark)

        metrics.append(
            {
                "criterion_id": criterion_id,
                "criterion_name": criterion["name"],
                "score": score,
                "benchmark_score": benchmark,
                "criterion_gap": criterion_gap,
                "relative_performance_percent": relative_percent,
            }
        )

    return metrics


def _parse_submission_date(raw_date: str) -> date:
    return date.fromisoformat(raw_date)


def rank_suppliers(
    supplier_payloads: list[dict[str, Any]],
    active_criteria: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    all_evaluations = [item["evaluations"] for item in supplier_payloads]
    criterion_benchmarks = calculate_criterion_benchmarks(all_evaluations, active_criteria)

    scored_rows: list[dict[str, Any]] = []
    for item in supplier_payloads:
        evaluations = item["evaluations"]
        absolute_score = calculate_absolute_weighted_score(evaluations, active_criteria)
        ppi = calculate_ppi(evaluations, active_criteria, criterion_benchmarks)
        criterion_metrics = build_criterion_metrics(evaluations, active_criteria, criterion_benchmarks)

        scored_rows.append(
            {
                "supplier_name": item["supplier_name"],
                "submission_date": item["submission_date"],
                "experience_rating": int(item["experience_rating"]),
                "absolute_score": absolute_score,
                "ppi": ppi,
                "criterion_metrics": criterion_metrics,
                "evaluations": evaluations,
            }
        )

    ranked_rows = sorted(
        scored_rows,
        key=lambda row: (
            -row["ppi"],
            _parse_submission_date(row["submission_date"]),
            -row["experience_rating"],
            row["supplier_name"].lower(),
        ),
    )

    for index, row in enumerate(ranked_rows, start=1):
        row["final_rank"] = index

    return ranked_rows

