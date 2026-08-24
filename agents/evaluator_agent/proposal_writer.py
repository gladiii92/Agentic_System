"""
agents/evaluator_agent/proposal_writer.py

VERSION 4 (2026-08-24, zeilengenauer Umbau): schreibt jetzt nur noch einen
kleinen Kontext-Ausschnitt um EINE Zielzeile, siehe proposal_writer_prompt.py
Version 4 und line_context_extractor.py.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import requests

from agents.evaluator_agent.proposal_writer_prompt import build_proposal_writer_prompt

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5:latest"


class ProposalWriterError(Exception):
    """Fehler beim Ollama-Aufruf oder beim Parsen der Antwort."""


@dataclass(frozen=True)
class WrittenContextProposal:
    filename: str
    target_line_number: int
    updated_context_text: str
    change_summary: str


def write_context_proposal(
    filename: str,
    target_line_number: int,
    numbered_context_text: str,
    contradiction_summary: str,
    suggested_update: str,
    current_project_concept: str,
    rejection_examples: list[str] | None = None,
    model: str = DEFAULT_MODEL,
    timeout_seconds: int = 90,
) -> WrittenContextProposal:
    prompt = build_proposal_writer_prompt(
        filename=filename,
        target_line_number=target_line_number,
        numbered_context_text=numbered_context_text,
        contradiction_summary=contradiction_summary,
        suggested_update=suggested_update,
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
        return WrittenContextProposal(
            filename=filename,
            target_line_number=target_line_number,
            updated_context_text=parsed["updated_context_text"],
            change_summary=parsed["change_summary"],
        )
    except KeyError as exc:
        raise ProposalWriterError(
            f"Ollama-Antwort fuer {filename} fehlt erwartetes Feld: {exc}.\nRohantwort: {raw_text[:500]}"
        ) from exc
