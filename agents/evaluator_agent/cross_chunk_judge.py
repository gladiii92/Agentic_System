"""Cross‑Chunk Audit Judge wrapper.

Reuses the local Ollama client (same as run_full_audit_judge) to evaluate
evidence statements collected from multiple document chunks.
"""

from __future__ import annotations

import json
import requests
from dataclasses import dataclass

from patching.cross_chunk_judge_prompt import build_cross_chunk_judge_prompt

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5-coder:latest"
DEFAULT_NUM_CTX = 8192


class CrossChunkJudgeError(Exception):
    """Fehler beim Cross-Chunk-Judge-Aufruf oder beim Parsen der Antwort."""


@dataclass(frozen=True)
class CrossChunkJudgment:
    is_meaningful: bool
    is_supported: bool
    severity: str
    reasoning: str
    contradiction_summary: str


def run_cross_chunk_judge(
    evidence_items: list[str],
    model: str = DEFAULT_MODEL,
    num_ctx: int = DEFAULT_NUM_CTX,
    timeout_seconds: int = 90,
) -> CrossChunkJudgment:
    """
    Send the collected evidence items to the cross‑chunk judge LLM
    and return a structured judgment.
    """
    if not evidence_items:
        return CrossChunkJudgment(
            is_meaningful=False,
            is_supported=True,
            severity="LOW",
            reasoning="Keine Evidence-Aussagen vorhanden.",
            contradiction_summary="",
        )

    prompt = build_cross_chunk_judge_prompt(evidence_items)

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "format": "json",
                "options": {"temperature": 0, "num_ctx": num_ctx},
                "stream": False,
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise CrossChunkJudgeError("Ollama nicht erreichbar unter localhost:11434.") from exc
    except requests.exceptions.Timeout as exc:
        raise CrossChunkJudgeError(f"Ollama Timeout nach {timeout_seconds}s.") from exc
    except requests.exceptions.HTTPError as exc:
        raise CrossChunkJudgeError(f"Ollama HTTP-Fehler: {exc}") from exc

    raw_text = response.json().get("response", "")

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise CrossChunkJudgeError(
            f"Ollama-Antwort ist kein valides JSON:\n{raw_text[:500]}"
        ) from exc

    try:
        return CrossChunkJudgment(
            is_meaningful=bool(parsed["is_meaningful"]),
            is_supported=bool(parsed["is_supported"]),
            severity=parsed["severity"],
            reasoning=parsed["reasoning"],
            contradiction_summary=parsed.get("contradiction_summary", ""),
        )
    except KeyError as exc:
        raise CrossChunkJudgeError(
            f"Ollama-Antwort fehlt erwartetes Feld: {exc}.\nRohantwort: {raw_text[:500]}"
        ) from exc