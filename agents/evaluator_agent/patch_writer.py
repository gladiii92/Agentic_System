"""
agents/evaluator_agent/patch_writer.py

VERSION 2 (2026-08-26, Vollkontext-Ergaenzung -- siehe Chat-Verlauf und
patch_writer_prompt.py-Docstring fuer die volle Begruendung).

Aenderung gegenueber der Version vom 2026-08-25:
- write_patch() bekommt einen neuen Pflichtparameter full_document_text:
  str -- der volle aktuelle Text derselben Datei. Wird durchgereicht an
  build_patch_writer_prompt(), damit das Modell die tatsaechlich zu
  korrigierende Stelle im GANZEN Dokument finden kann, nicht nur
  innerhalb des kleinen Hunks.
- Ollama-Request setzt jetzt explizit "num_ctx": 8192 (siehe evaluator.py
  fuer dieselbe Begruendung -- verhindert lautloses Abschneiden des
  laengeren Prompts durch Ollamas kleines Default-Kontextfenster).

WICHTIG: die harte Sicherheitsschicht (patching/patch_validator.py)
bleibt UNVERAENDERT und wird weiterhin auf JEDEN von hier zurueckgegebenen
ProposedPatch angewendet, bevor irgendetwas angezeigt oder geschrieben
wird -- dieser Vollkontext-Fix ersetzt NICHT die Validierung, er soll nur
die Trefferquote plausibler Vorschlaege verbessern.
"""

from __future__ import annotations

import json

import requests

from agents.evaluator_agent.patch_writer_prompt import build_patch_writer_prompt
from patching.patch_models import ProposedPatch

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5-coder:latest"
DEFAULT_NUM_CTX = 8192


class PatchWriterError(Exception):
    """Fehler beim Ollama-Aufruf oder beim Parsen der Antwort."""


def write_patch(
    filename: str,
    contradiction_summary: str,
    hunk_diff_text: str,
    current_project_concept: str,
    full_document_text: str,
    rejection_examples: list[str] | None = None,
    model: str = DEFAULT_MODEL,
    timeout_seconds: int = 90,
    num_ctx: int = DEFAULT_NUM_CTX,
) -> ProposedPatch:
    prompt = build_patch_writer_prompt(
        filename=filename,
        contradiction_summary=contradiction_summary,
        hunk_diff_text=hunk_diff_text,
        current_project_concept=current_project_concept,
        full_document_text=full_document_text,
        rejection_examples=rejection_examples,
    )

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
