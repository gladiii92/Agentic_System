"""
patching/diff_hunks.py

Deterministischer Diff-Hunk-Builder (2026-08-25, kompletter Neuaufbau --
siehe Chat-Verlauf: "3 Stunden im Kreis gedreht" mit LLM-basierter
Lokalisierung, jetzt Umstieg auf Pythons eigenes difflib als primaeren,
deterministischen Aenderungsfinder statt Embedding-Aehnlichkeit oder
LLM-Zeilennummern).

KERNIDEE: Wenn wir bereits VORHER-Text und NACHHER-Text einer Datei haben
(aus snapshot_store.py), muessen wir NICHT raten, WO sich etwas geaendert
hat -- difflib.SequenceMatcher liefert das exakt und kostenlos. Ein LLM
wird erst danach gebraucht, um zu URTEILEN, OB eine gefundene Aenderung
fachlich sinnvoll/ausreichend ist -- nicht mehr, um die Aenderung selbst
zu FINDEN.

Das eliminiert die gesamte Fehlerklasse aus den vorherigen Versuchen:
falsche Abschnittswahl, Uebergeneralisierung auf Nachbarzeilen,
unmotivierte Wortaenderungen ausserhalb der Zielzeile -- all das entstand,
weil ein LLM freien Text produzieren durfte. Hier produziert das LLM
NIE mehr den finalen Text direkt; es bewertet nur JSON-Metadaten zu
bereits deterministisch gefundenen Hunks (siehe patch_judge_prompt.py).
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass


@dataclass(frozen=True)
class DiffHunk:
    """Ein zusammenhaengender Aenderungsblock zwischen zwei Textversionen.
    Zeilennummern sind 1-basiert und beziehen sich auf den JEWEILS
    aktuellen (neuen) Text -- das ist der Text, der spaeter tatsaechlich
    bearbeitet wird."""

    old_start_line: int
    old_end_line: int  # exklusiv
    new_start_line: int
    new_end_line: int  # exklusiv
    old_lines: list[str]
    new_lines: list[str]
    context_before: list[str]
    context_after: list[str]


def _get_context(lines: list[str], start_idx: int, end_idx: int, context_size: int) -> tuple[list[str], list[str]]:
    before_start = max(0, start_idx - context_size)
    after_end = min(len(lines), end_idx + context_size)
    return lines[before_start:start_idx], lines[end_idx:after_end]


def compute_diff_hunks(old_text: str, new_text: str, context_lines: int = 3) -> list[DiffHunk]:
    """Berechnet alle zusammenhaengenden Aenderungsbloecke zwischen zwei
    Textversionen mittels difflib.SequenceMatcher (Standardbibliothek,
    keine Zusatzabhaengigkeit, deterministisch, kein LLM-Aufruf).

    context_lines: wie viele unveraenderte Zeilen vor/nach jedem Hunk als
    Kontext mitgeliefert werden (Standard 3, kleiner als die frueheren
    5 Zeilen, weil wir jetzt EXAKTE Blockgrenzen haben statt geschaetzter
    Zeilennummern -- weniger Kontext-Puffer noetig)."""
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()

    matcher = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    hunks = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue

        context_before, _ = _get_context(new_lines, j1, j2, context_lines)
        _, context_after = _get_context(new_lines, j1, j2, context_lines)

        hunks.append(
            DiffHunk(
                old_start_line=i1 + 1,
                old_end_line=i2 + 1,
                new_start_line=j1 + 1,
                new_end_line=j2 + 1,
                old_lines=old_lines[i1:i2],
                new_lines=new_lines[j1:j2],
                context_before=context_before,
                context_after=context_after,
            )
        )

    return hunks


def render_hunk_for_prompt(hunk: DiffHunk) -> str:
    """Formatiert einen Hunk lesbar fuer einen LLM-Prompt: Kontext davor,
    dann die Aenderung im klassischen Diff-Stil (- alt, + neu), Kontext
    danach. Der Judge sieht NUR das -- keinen Grund, weiter draussen im
    Dokument zu spekulieren."""
    lines = []
    lines.extend(f"  {line}" for line in hunk.context_before)
    lines.extend(f"- {line}" for line in hunk.old_lines)
    lines.extend(f"+ {line}" for line in hunk.new_lines)
    lines.extend(f"  {line}" for line in hunk.context_after)
    return "\n".join(lines)
