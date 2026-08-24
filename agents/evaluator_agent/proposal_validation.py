"""
agents/evaluator_agent/proposal_validation.py

VERSION 2 (2026-08-24, zeilengenauer Umbau): Checks bleiben inhaltlich
gleich (Laengenverhaeltnis, Prompt-Leak-Marker), werden aber jetzt auf
den kleinen Zeilen-Kontext-Ausschnitt angewendet statt auf einen ganzen
Abschnitt -- die Grenzen (MAX/MIN_LENGTH_RATIO) bleiben unveraendert
sinnvoll, da sie relative Verhaeltnisse sind, keine absoluten Groessen.

ZUSAETZLICHER NEUER CHECK (line_count_check): bei einem so kleinen,
praezise umrissenen Ausschnitt ist ein sehr starker Hinweis auf ein
Problem, wenn sich die ANZAHL der Zeilen im Ausschnitt aendert -- unser
Prompt verlangt explizit "gib ALLE Zeilen des Kontexts zurueck", eine
abweichende Zeilenzahl deutet auf eine ignorierte Anweisung hin.
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_LENGTH_RATIO = 1.5
MIN_LENGTH_RATIO = 0.5
MAX_LINE_COUNT_DELTA = 2  # Ausschnitt darf max. 2 Zeilen mehr/weniger haben als das Original

PROMPT_LEAK_MARKERS = [
    "antworte ausschließlich",
    "wichtige einschränkungen",
    "erzeuge den korrigierten text",
    "json-objekt exakt in dieser struktur",
    "tatsächlicher, aktueller gesamtprojektstand",
    "beginn ausschnitt",
    "ende ausschnitt",
]


@dataclass(frozen=True)
class ValidationResult:
    passed: bool
    failures: list[str]


def validate_updated_context(original_context_text: str, updated_context_text: str) -> ValidationResult:
    """original_context_text ist hier context_text_plain aus LineContext
    (OHNE Zeilennummern-Praefixe) -- muss also mit dem verglichen werden,
    was der Writer zurueckgibt (ebenfalls ohne Praefixe laut Prompt-Vorgabe)."""
    failures: list[str] = []

    length_ratio = len(updated_context_text) / max(len(original_context_text), 1)
    if length_ratio > MAX_LENGTH_RATIO:
        failures.append(
            f"Ausschnitt ist {length_ratio:.1f}x so lang wie das Original "
            f"(Grenze: {MAX_LENGTH_RATIO}x) -- moeglicher Prompt-Leak oder Wiederholungsfehler."
        )
    if length_ratio < MIN_LENGTH_RATIO:
        failures.append(
            f"Ausschnitt ist nur {length_ratio:.1f}x so lang wie das Original "
            f"(Grenze: {MIN_LENGTH_RATIO}x) -- moeglicher Textverlust."
        )

    original_line_count = len(original_context_text.splitlines())
    updated_line_count = len(updated_context_text.splitlines())
    line_delta = abs(updated_line_count - original_line_count)
    if line_delta > MAX_LINE_COUNT_DELTA:
        failures.append(
            f"Zeilenanzahl im Ausschnitt hat sich um {line_delta} Zeilen veraendert "
            f"(Original: {original_line_count}, Vorschlag: {updated_line_count}, "
            f"Grenze: {MAX_LINE_COUNT_DELTA}) -- moegliche unvollstaendige Uebernahme."
        )

    lower_text = updated_context_text.lower()
    for marker in PROMPT_LEAK_MARKERS:
        if marker in lower_text:
            failures.append(f"Verdacht auf Prompt-Leak: Phrase '{marker}' im Ergebnistext gefunden.")

    if not updated_context_text.strip():
        failures.append("Vorschlag ist leer.")

    return ValidationResult(passed=not failures, failures=failures)
