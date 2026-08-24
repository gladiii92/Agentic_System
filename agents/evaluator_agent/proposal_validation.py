"""
agents/evaluator_agent/proposal_validation.py

Deterministische Sicherheits-Checks (KEIN LLM) fuer einen von Ollama
erzeugten updated_section_text, BEVOR er dem Nutzer angezeigt wird. Siehe
Chat-Verlauf 2026-08-24: nach einem realen Fehlerfall (Prompt-Leck,
massiver Textverlust) wurde entschieden, eine deterministische Vorprueung
einzuziehen -- exakt das "cheap deterministic tests first"-Prinzip aus der
Kaskaden-Architektur (embedding_filter.py), jetzt auf der Schreibseite
angewendet statt nur auf der Erkennungsseite.

Jeder Check hier ist bewusst simpel und erklaerbar -- kein ML, nur klare
Regeln, die ein Nutzer beim Lesen sofort nachvollziehen kann.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_LENGTH_RATIO = 1.5  # neuer Text darf max. 50% laenger sein als das Original
MIN_LENGTH_RATIO = 0.5  # neuer Text darf max. 50% kuerzer sein als das Original

# Phrasen, die typischerweise NUR im Prompt selbst vorkommen -- wenn sie im
# Ergebnis auftauchen, ist das ein starkes Signal fuer ein Prompt-Leck
# (siehe realer Fehlerfall: "Antworte ausschließlich mit einem JSON-Objekt"
# tauchte im Ergebnistext auf).
PROMPT_LEAK_MARKERS = [
    "antworte ausschließlich",
    "wichtige einschränkungen",
    "erzeuge den korrigierten text",
    "json-objekt exakt in dieser struktur",
    "tatsächlicher, aktueller gesamtprojektstand",
]


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    failures: list[str]


def validate_updated_section(original_section_text: str, updated_section_text: str) -> ValidationResult:
    """Fuehrt alle deterministischen Checks aus. passed=False bedeutet:
    der Vorschlag wird NICHT dem Nutzer angezeigt, sondern automatisch
    verworfen (siehe run_drift_check.py) -- unabhaengig vom LLM-Judge-
    Score, weil dieser Score sich auf die ERKENNUNG bezog, nicht auf die
    tatsaechliche Qualitaet DIESES konkreten Schreibvorschlags."""
    failures: list[str] = []

    length_ratio = len(updated_section_text) / max(len(original_section_text), 1)
    if length_ratio > MAX_LENGTH_RATIO:
        failures.append(
            f"Vorschlag ist {length_ratio:.1f}x so lang wie das Original "
            f"(Grenze: {MAX_LENGTH_RATIO}x) -- moeglicher Prompt-Leak oder Wiederholungsfehler."
        )
    if length_ratio < MIN_LENGTH_RATIO:
        failures.append(
            f"Vorschlag ist nur {length_ratio:.1f}x so lang wie das Original "
            f"(Grenze: {MIN_LENGTH_RATIO}x) -- moeglicher Textverlust."
        )

    lower_text = updated_section_text.lower()
    for marker in PROMPT_LEAK_MARKERS:
        if marker in lower_text:
            failures.append(f"Verdacht auf Prompt-Leak: Phrase '{marker}' im Ergebnistext gefunden.")

    if not updated_section_text.strip():
        failures.append("Vorschlag ist leer.")

    return ValidationResult(passed=not failures, failures=failures)
