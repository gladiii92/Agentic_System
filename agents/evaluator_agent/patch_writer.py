"""
agents/evaluator_agent/patch_writer.py

NEUES Modul (2026-08-25, ersetzt proposal_writer.py komplett). Ruft den
Patch-Writer-Prompt auf und liefert einen ProposedPatch (noch NICHT
validiert -- siehe patching/patch_validator.py fuer den naechsten
Pflichtschritt vor jeder Anzeige/Anwendung).
"""

from __future__ import annotations

import json

import requests

from agents.evaluator_agent.patch_writer_prompt import build_patch_writer_prompt
from patching.patch_models import ProposedPatch

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5:latest"


class PatchWriterError(Exception):
    """Fehler beim Ollama-Aufruf oder beim Parsen der Antwort."""


def write_patch(
    filename: str,
    contradiction_summary: str,
    hunk_diff_text: str,
    current_project_concept: str,
    rejection_examples: list[str] | None = None,
    model: str = DEFAULT_MODEL,
    timeout_seconds: int = 90,
) -> ProposedPatch:
    prompt = build_patch_writer_prompt(
        filename=filename,
        contradiction_summary=contradiction_summary,
        hunk_diff_text=hunk_diff_text,
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
        raise PatchWriterError("Ollama nicht erreichbar unter localhost:11434.") from exc
    except requests.exceptions.Timeout as exc:
        raise PatchWriterError(f"Ollama Timeout nach {timeout_seconds}s fuer {filename}.") from exc
    except requests.exceptions.HTTPError as exc:
        raise PatchWriterError(f"Ollama HTTP-Fehler fuer {filename}: {exc}") from exc

    raw_text = response.json().get("response", "")

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise PatchWriterError(
            f"Ollama-Antwort fuer {filename} ist kein valides JSON:\n{raw_text[:500]}"
        ) from exc

    try:
        return ProposedPatch(
            filename=filename,
            exact_old_text=parsed["exact_old_text"],
            replacement_text=parsed["replacement_text"],
            change_summary=parsed["change_summary"],
        )
    except KeyError as exc:
        raise PatchWriterError(
            f"Ollama-Antwort fuer {filename} fehlt erwartetes Feld: {exc}.\nRohantwort: {raw_text[:500]}"
        ) from exc
