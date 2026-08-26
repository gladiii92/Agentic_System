"""
agents/evaluator_agent/patch_writer.py

VERSION 3 (2026-08-26, Cloud-Eskalation -- siehe Chat-Verlauf und
model_clients.py-Docstring fuer die volle Begruendung).

Aenderung gegenueber Version 2 (Vollkontext-Fix, selbes Datum, Vormittag):
write_patch() bekommt einen neuen Parameter model_tier: str mit den
erlaubten Werten "ollama" (Standard, unveraendertes Verhalten),
"gemini", "groq". Der Prompt-Aufbau (build_patch_writer_prompt) bleibt
FUER ALLE DREI STUFEN IDENTISCH -- nur der Transport zum jeweiligen
Modell unterscheidet sich. Das haelt die Prompt-Logik an einer Stelle,
statt sie pro Anbieter zu duplizieren.

WICHTIG: welche Stufe wann versucht wird (Eskalations-Reihenfolge:
ollama -> gemini -> groq, ausgeloest durch fehlgeschlagene Validierung),
entscheidet run_drift_check.py -- dieses Modul liefert nur EINEN
Patch-Versuch pro Aufruf, unabhaengig von der Stufe.
"""

from __future__ import annotations

import json

import requests

from agents.evaluator_agent.model_clients import ModelClientError, call_gemini, call_groq
from agents.evaluator_agent.patch_writer_prompt import build_patch_writer_prompt
from patching.patch_models import ProposedPatch

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5-coder:latest"
DEFAULT_NUM_CTX = 8192

VALID_MODEL_TIERS = ("ollama", "gemini", "groq")


class PatchWriterError(Exception):
    """Fehler beim Modell-Aufruf (egal welcher Anbieter) oder beim Parsen der Antwort."""


def _call_ollama(prompt: str, model: str, timeout_seconds: int, num_ctx: int) -> str:
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
        raise PatchWriterError(f"Ollama Timeout nach {timeout_seconds}s.") from exc
    except requests.exceptions.HTTPError as exc:
        raise PatchWriterError(f"Ollama HTTP-Fehler: {exc}") from exc

    return response.json().get("response", "")


def write_patch(
    filename: str,
    contradiction_summary: str,
    hunk_diff_text: str,
    current_project_concept: str,
    full_document_text: str,
    rejection_examples: list[str] | None = None,
    model_tier: str = "ollama",
    model: str | None = None,
    timeout_seconds: int = 90,
    num_ctx: int = DEFAULT_NUM_CTX,
) -> ProposedPatch:
    """Erzeugt EINEN Patch-Vorschlag ueber die per model_tier gewaehlte
    Stufe ("ollama", "gemini" oder "groq"). Der Prompt ist fuer alle drei
    Stufen identisch, nur der Transport unterscheidet sich.

    Wird von run_drift_check.py in einer Eskalationsschleife aufgerufen:
    bei fehlgeschlagener Validierung wird write_patch() ERNEUT mit der
    naechsten Stufe aufgerufen, nicht automatisch von hier aus."""
    if model_tier not in VALID_MODEL_TIERS:
        raise PatchWriterError(f"Unbekannte model_tier '{model_tier}', erlaubt: {VALID_MODEL_TIERS}")

    prompt = build_patch_writer_prompt(
        filename=filename,
        contradiction_summary=contradiction_summary,
        hunk_diff_text=hunk_diff_text,
        current_project_concept=current_project_concept,
        full_document_text=full_document_text,
        rejection_examples=rejection_examples,
    )

    try:
        if model_tier == "ollama":
            raw_text = _call_ollama(prompt, model or DEFAULT_MODEL, timeout_seconds, num_ctx)
        elif model_tier == "gemini":
            raw_text = call_gemini(prompt, model=model) if model else call_gemini(prompt)
        else:  # "groq"
            raw_text = call_groq(prompt, model=model) if model else call_groq(prompt)
    except ModelClientError as exc:
        raise PatchWriterError(f"Fehler bei Stufe '{model_tier}' fuer {filename}: {exc}") from exc

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise PatchWriterError(
            f"Antwort von Stufe '{model_tier}' fuer {filename} ist kein valides JSON:\n{raw_text[:500]}"
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
            f"Antwort von Stufe '{model_tier}' fuer {filename} fehlt erwartetes Feld: {exc}.\nRohantwort: {raw_text[:500]}"
        ) from exc
