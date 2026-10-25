from __future__ import annotations

import json
from urllib import request
from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field, ValidationError

try:
    from openai import OpenAI
except ImportError:  # pragma: no cover - optional dependency at runtime
    OpenAI = None

try:
    from google import genai as google_genai
except ImportError:  # pragma: no cover - optional dependency at runtime
    google_genai = None


class CriterionEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    criterion_id: int
    score: float
    justification: str = Field(min_length=1)
    evidence: str = Field(min_length=1)


class LLMEvaluationPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    evaluations: list[CriterionEvaluation]


class NormalizedCriterionEvaluation(BaseModel):
    criterion_id: int
    score: float
    max_score: int
    justification: str
    evidence: str


class NormalizedEvaluationResult(BaseModel):
    evaluations: list[NormalizedCriterionEvaluation]
    dropped_items: int
    clipped_scores: int
    backfilled_items: int
    raw_payload: dict[str, Any]


@dataclass(frozen=True)
class CriterionContext:
    criterion_id: int
    max_score: int
    name: str


def build_evaluation_prompt(extracted_text: str, active_criteria: list[dict[str, Any]]) -> str:
    criteria_lines = []
    for criterion in active_criteria:
        criteria_lines.append(
            f"- criterion_id={criterion['criterion_id']}, "
            f"name={criterion['name']}, "
            f"max_score={criterion['max_score']}, "
            f"description={criterion['description']}"
        )

    criteria_block = "\n".join(criteria_lines)
    return (
        "You are evaluating an RFP supplier response. "
        "Return valid JSON only with top-level key 'evaluations', where each item has: "
        "criterion_id (int), score (number), justification (string), evidence (string). "
        "Use only provided criterion_id values.\n\n"
        f"Criteria:\n{criteria_block}\n\n"
        f"Supplier Response Text:\n{extracted_text}"
    )


def _coerce_raw_payload(raw_response: Any) -> dict[str, Any]:
    if isinstance(raw_response, dict):
        return raw_response
    if isinstance(raw_response, str):
        return json.loads(raw_response)
    raise TypeError("LLM response must be dict or JSON string")


def normalize_llm_payload(raw_response: Any, active_criteria: list[dict[str, Any]]) -> NormalizedEvaluationResult:
    raw_payload = _coerce_raw_payload(raw_response)
    criteria_by_id: dict[int, CriterionContext] = {
        int(criterion["criterion_id"]): CriterionContext(
            criterion_id=int(criterion["criterion_id"]),
            max_score=int(criterion["max_score"]),
            name=str(criterion["name"]),
        )
        for criterion in active_criteria
    }

    evaluations_raw = raw_payload.get("evaluations", [])
    if not isinstance(evaluations_raw, list):
        evaluations_raw = []

    normalized_by_id: dict[int, NormalizedCriterionEvaluation] = {}
    dropped_items = 0
    clipped_scores = 0

    for item in evaluations_raw:
        try:
            parsed = CriterionEvaluation.model_validate(item)
        except ValidationError:
            dropped_items += 1
            continue

        criterion = criteria_by_id.get(parsed.criterion_id)
        if criterion is None:
            dropped_items += 1
            continue

        clipped_score = min(max(parsed.score, 0.0), float(criterion.max_score))
        if clipped_score != parsed.score:
            clipped_scores += 1

        normalized_by_id[parsed.criterion_id] = NormalizedCriterionEvaluation(
            criterion_id=parsed.criterion_id,
            score=clipped_score,
            max_score=criterion.max_score,
            justification=parsed.justification,
            evidence=parsed.evidence,
        )

    backfilled_items = 0
    for criterion in criteria_by_id.values():
        if criterion.criterion_id in normalized_by_id:
            continue
        backfilled_items += 1
        normalized_by_id[criterion.criterion_id] = NormalizedCriterionEvaluation(
            criterion_id=criterion.criterion_id,
            score=0.0,
            max_score=criterion.max_score,
            justification="No valid justification returned by LLM for this criterion.",
            evidence="No valid evidence returned by LLM for this criterion.",
        )

    ordered_evaluations = [
        normalized_by_id[int(criterion["criterion_id"])]
        for criterion in sorted(active_criteria, key=lambda item: int(item["criterion_id"]))
    ]

    return NormalizedEvaluationResult(
        evaluations=ordered_evaluations,
        dropped_items=dropped_items,
        clipped_scores=clipped_scores,
        backfilled_items=backfilled_items,
        raw_payload=raw_payload,
    )


def call_openai_for_evaluation(
    prompt: str,
    model: str = "gpt-4o-mini",
    api_key: str | None = None,
) -> dict[str, Any]:
    if OpenAI is None:
        raise RuntimeError("openai package is not installed. Run: pip install -r requirements.txt")

    if not api_key:
        raise RuntimeError("API key is required for OpenAI evaluations.")

    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model,
        input=prompt,
        text={"format": {"type": "json_object"}},
    )

    return json.loads(response.output_text)


def call_gemini_for_evaluation(
    prompt: str,
    model: str = "gemini-2.0-flash",
    api_key: str | None = None,
) -> dict[str, Any]:
    if google_genai is None:
        raise RuntimeError("google-genai package is not installed. Run: pip install -r requirements.txt")

    if not api_key:
        raise RuntimeError("API key is required for Gemini evaluations.")

    client = google_genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )

    if not getattr(response, "text", None):
        raise RuntimeError("Gemini returned an empty response.")
    return json.loads(response.text)


def call_ollama_for_evaluation(
    prompt: str,
    model: str = "llama3.1",
    base_url: str = "http://localhost:11434",
) -> dict[str, Any]:
    endpoint = f"{base_url.rstrip('/')}/api/generate"
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": "json",
    }

    req = request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with request.urlopen(req, timeout=180) as response:
            body = response.read().decode("utf-8")
    except Exception as error:  # pragma: no cover - network/runtime dependent
        raise RuntimeError(f"Ollama request failed: {error}") from error

    parsed = json.loads(body)
    raw_text = parsed.get("response", "")
    if not raw_text:
        raise RuntimeError("Ollama returned an empty response.")
    return json.loads(raw_text)


def evaluate_with_validation_gate(
    extracted_text: str,
    active_criteria: list[dict[str, Any]],
    llm_callable: Callable[[str], Any] | None = None,
    provider: str = "openai",
    model: str = "gpt-4o-mini",
    ollama_base_url: str = "http://localhost:11434",
    api_key: str | None = None,
) -> NormalizedEvaluationResult:
    prompt = build_evaluation_prompt(extracted_text=extracted_text, active_criteria=active_criteria)

    if llm_callable is not None:
        raw_response = llm_callable(prompt)
    else:
        normalized_provider = provider.strip().lower()
        if normalized_provider == "openai":
            raw_response = call_openai_for_evaluation(prompt=prompt, model=model, api_key=api_key)
        elif normalized_provider == "gemini":
            raw_response = call_gemini_for_evaluation(prompt=prompt, model=model, api_key=api_key)
        elif normalized_provider == "ollama":
            raw_response = call_ollama_for_evaluation(prompt=prompt, model=model, base_url=ollama_base_url)
        else:
            raise ValueError(f"Unsupported provider '{provider}'. Use one of: openai, gemini, ollama.")

    return normalize_llm_payload(raw_response=raw_response, active_criteria=active_criteria)

