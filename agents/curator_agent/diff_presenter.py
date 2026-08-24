"""
agents/curator_agent/diff_presenter.py

Baut eine einfache Vorher/Nachher-Textanzeige (kein farbiger Diff, siehe
Chat-Verlauf 2026-08-24: "ein einfacher vorher/nachher-Text wuerde erst
einmal reichen") mittels des in Python eingebauten difflib-Moduls.
Bewusst als eigenstaendiges, kleines Modul -- wird sowohl vom Curator
als auch spaeter potenziell vom Builder-Agenten fuer Code-Diffs genutzt
werden koennen (unifed_diff ist generisch fuer beliebigen Text).
"""

from __future__ import annotations

import difflib


def build_unified_diff(original_text: str, updated_text: str, filename: str) -> str:
    """Erzeugt einen klassischen unified-diff-Text (wie 'git diff'),
    lesbar in jeder Konsole ohne Zusatzbibliothek."""
    original_lines = original_text.splitlines(keepends=True)
    updated_lines = updated_text.splitlines(keepends=True)

    diff = difflib.unified_diff(
        original_lines,
        updated_lines,
        fromfile=f"{filename} (aktuell)",
        tofile=f"{filename} (Vorschlag)",
        lineterm="",
    )
    return "\n".join(diff)


def has_actual_changes(original_text: str, updated_text: str) -> bool:
    """Prueft, ob der Vorschlag ueberhaupt etwas veraendert -- Sicherheits-
    check, falls der Ollama-Aufruf versehentlich den identischen Text
    zurueckgibt (waere ein leerer, nutzloser Diff)."""
    return original_text.strip() != updated_text.strip()
