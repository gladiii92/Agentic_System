"""
agents/curator_agent/line_context_extractor.py

NEUES Modul (2026-08-24, siehe Chat-Verlauf) -- ersetzt section_locator.py
fuer die Lokalisierungsaufgabe. Schneidet fuer eine EXAKTE, vom Judge
gelieferte Zeilennummer einen kleinen Kontext-Ausschnitt (Standard: 5
Zeilen davor, 5 Zeilen danach) aus dem Volltext aus -- deterministisch,
kein Raten mehr per Wortueberlappung.

WARUM section_locator.py's Wortueberlappungs-Ansatz ERSETZT statt nur
gepatcht wird: die Nutzer-Anforderung ist zeilengenaue Lokalisierung fuer
JEDE einzelne Diskrepanz in einem Dokument, nicht nur fuer die erste/
groesste. Ein Abschnitts-Ansatz kann das strukturell nicht leisten (ein
Abschnitt kann mehrere unabhaengige Diskrepanzen enthalten, ein einzelner
Kontext-Ausschnitt pro Zeile aber schon).

Mehrfach-Aenderungen im selben Dokument werden von run_drift_check.py
verwaltet: JEDE Zeile mit einem Finding bekommt ihren EIGENEN Kontext-
Ausschnitt, EIGENEN Writer-Aufruf, EIGENE Human-in-the-Loop-Bestaetigung.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_CONTEXT_LINES_BEFORE = 5
DEFAULT_CONTEXT_LINES_AFTER = 5


@dataclass(frozen=True)
class LineContext:
    target_line_number: int  # 1-basiert, wie vom Judge geliefert
    context_start_line: int  # 1-basiert, erste Zeile im Ausschnitt
    context_end_line: int  # 1-basiert, letzte Zeile im Ausschnitt
    context_text: str  # der Ausschnitt-Text, MIT Zeilennummern (fuer den Writer-Prompt)
    context_text_plain: str  # der Ausschnitt-Text, OHNE Zeilennummern (fuer den finalen Zusammenbau)


def extract_context(
    full_text: str,
    target_line_number: int,
    lines_before: int = DEFAULT_CONTEXT_LINES_BEFORE,
    lines_after: int = DEFAULT_CONTEXT_LINES_AFTER,
) -> LineContext:
    """Schneidet target_line_number ± lines_before/lines_after aus dem
    Volltext aus. 1-basierte Zeilennummerierung (Zeile 1 = erste Zeile),
    konsistent mit drift_judge_prompt.number_lines()."""
    lines = full_text.splitlines()
    total_lines = len(lines)

    if target_line_number < 1 or target_line_number > total_lines:
        raise ValueError(
            f"target_line_number {target_line_number} liegt ausserhalb des Dokuments "
            f"(1 bis {total_lines})."
        )

    start_line = max(1, target_line_number - lines_before)
    end_line = min(total_lines, target_line_number + lines_after)

    selected_lines = lines[start_line - 1 : end_line]

    numbered_text = "\n".join(
        f"{start_line + i}: {line}" for i, line in enumerate(selected_lines)
    )
    plain_text = "\n".join(selected_lines)

    return LineContext(
        target_line_number=target_line_number,
        context_start_line=start_line,
        context_end_line=end_line,
        context_text=numbered_text,
        context_text_plain=plain_text,
    )


def replace_context_in_full_text(full_text: str, context: LineContext, new_plain_text: str) -> str:
    """Setzt den Volltext neu zusammen: Zeilen VOR context_start_line und
    NACH context_end_line bleiben unveraendert, nur der Zeilenbereich
    dazwischen wird durch new_plain_text ersetzt. Arbeitet zeilenbasiert
    (nicht zeichenbasiert wie section_locator.replace_section), da wir
    hier mit Zeilennummern arbeiten."""
    lines = full_text.splitlines(keepends=True)

    # keepends=True erhaelt die urspruenglichen Zeilenumbrueche (\n, \r\n)
    # jeder Zeile -- wichtig, um die Datei nicht versehentlich auf einen
    # anderen Zeilenumbruch-Stil umzustellen.
    before = lines[: context.context_start_line - 1]
    after = lines[context.context_end_line :]

    new_lines = new_plain_text.splitlines()
    # Zeilenumbruch-Stil vom Original uebernehmen (erste Zeile als Referenz,
    # falls vorhanden), sonst Standard-"\n".
    line_ending = "\n"
    if before and before[-1].endswith("\r\n"):
        line_ending = "\r\n"

    new_lines_with_endings = [line + line_ending for line in new_lines]

    return "".join(before) + "".join(new_lines_with_endings) + "".join(after)
