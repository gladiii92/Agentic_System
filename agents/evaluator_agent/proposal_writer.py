"""
agents/evaluator_agent/proposal_writer.py

Fuehrt den Ollama-Aufruf fuer proposal_writer_prompt.py aus und liefert
einen konkreten, einsetzbaren neuen Volltext fuer ein Vault-Dokument.
Analog im Aufbau zu evaluator.py (run_drift_judge), aber fuer die
Erzeugungs- statt die Bewertungs-Aufgabe.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import requests

from agents.evaluator_agent.proposal_writer_prompt import build_proposal_writer_prompt

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5-coder:latest"


class ProposalWriterError(Exception):
    """Fehler beim Ollama-Aufruf oder beim Parsen der Antwort."""


@dataclass(frozen=True)
class WrittenProposal:
    filename: str
    updated_full_text: str
    change_summary: str


def write_proposal(
    filename: str,
    contradiction_summary: str,
    suggested_update: str,
    original_full_text: str,
    current_project_concept: str,
    rejection_examples: list[str] | None = None,
    model: str = DEFAULT_MODEL,
    timeout_seconds: int = 180,
) -> WrittenProposal:
    prompt = build_proposal_writer_prompt(
        filename=filename,
        contradiction_summary=contradiction_summary,
        suggested_update=suggested_update,
        original_full_text=original_full_text,
        current_project_concept=current_project_concept,
        rejection_examples=rejection_examples,
    )

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "format": "json",
                "options": {"temperature": 0},
                "stream": False,
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise ProposalWriterError("Ollama nicht erreichbar unter localhost:11434.") from exc
    except requests.exceptions.Timeout as exc:
        raise ProposalWriterError(f"Ollama Timeout nach {timeout_seconds}s fuer {filename}.") from exc
    except requests.exceptions.HTTPError as exc:
        raise ProposalWriterError(f"Ollama HTTP-Fehler fuer {filename}: {exc}") from exc

    raw_text = response.json().get("response", "")

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ProposalWriterError(
            f"Ollama-Antwort fuer {filename} ist kein valides JSON:\n{raw_text[:500]}"
        ) from exc

    try:
        return WrittenProposal(
            filename=filename,
            updated_full_text=parsed["updated_full_text"],
            change_summary=parsed["change_summary"],
        )
    except KeyError as exc:
        raise ProposalWriterError(
            f"Ollama-Antwort fuer {filename} fehlt erwartetes Feld: {exc}.\nRohantwort: {raw_text[:500]}"
        ) from exc
