"""
patching/patch_models.py

Gemeinsame Datenstrukturen fuer den kompletten Patch-Workflow (2026-08-25).
Bewusst als eigenes, kleines Modul ohne Abhaengigkeiten zu anderen
Patch-Modulen -- verhindert zirkulaere Importe zwischen diff_hunks.py,
patch_validator.py, patch_applier.py.

KERNPRINZIP des gesamten Patch-Workflows (siehe Chat-Verlauf 2026-08-25,
Architektur-Entscheidung nach mehreren gescheiterten LLM-Freitext-Versuchen):
Ein Patch ist IMMER ein exact_old_text -> replacement_text Paar, NIEMALS
ein neu generierter Volltext oder Abschnitt. exact_old_text muss WORTWOERTLICH
und GENAU EINMAL im aktuellen Dokument vorkommen -- das macht die Anwendung
100% deterministisch und macht es UNMOEGLICH, dass ein Patch versehentlich
an einer anderen Stelle greift oder Nachbartext veraendert.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProposedPatch:
    """Ein vom Writer-Modell vorgeschlagener, aber noch NICHT validierter
    oder angewendeter Patch."""

    filename: str
    exact_old_text: str
    replacement_text: str
    change_summary: str


@dataclass(frozen=True)
class ValidatedPatch:
    """Ein Patch, der alle deterministischen Sicherheitschecks bestanden
    hat (siehe patch_validator.py) und dem Nutzer zur Bestaetigung
    vorgelegt werden darf."""

    filename: str
    exact_old_text: str
    replacement_text: str
    change_summary: str
    occurrence_start_index: int  # Zeichenposition im Volltext, fuer patch_applier.py


@dataclass(frozen=True)
class PatchApplicationResult:
    success: bool
    updated_full_text: str | None
    error_message: str | None
