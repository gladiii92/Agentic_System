"""
agents/curator_agent/drift_diff.py

Dritter Baustein des Curator-Agenten (Phase 1). Zweck: rein deterministischer
Vorab-Check zwischen zwei ConceptSummary-Staenden (vorheriger Snapshot vs.
aktueller Lauf), ANALOG zum Muster aus AI_Project_Reviewer/sync_fis.py
(diff_snapshots-Funktion) -- dort werden Datei-Strukturmetriken verglichen,
hier vergleichen wir die Textinhalte pro Dokument.

WICHTIG -- Rollentrennung (siehe Chat-Verlauf 2026-08-22/23):
Dieses Modul faellt bewusst KEIN inhaltliches Urteil ("widerspricht
ROADMAP.md dem echten Stand?") -- das braucht ein LLM (Ollama) und ist ein
spaeterer Baustein. Dieses Modul erkennt nur, WELCHE Dokumente sich
ueberhaupt textuell veraendert haben ODER deren zugrunde liegende Datei
sich veraendert hat (mtime), seit dem letzten Snapshot -- also die
Kandidatenliste dafuer, WAS ueberhaupt an den LLM-Check weitergereicht
werden muss. Das spart spaeter unnoetige Ollama-Aufrufe fuer Dokumente,
die sich offensichtlich gar nicht veraendert haben.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agents.curator_agent.concept_loader import ConceptSummary


@dataclass(frozen=True)
class DriftCandidate:
    """Ein Dokument, das sich seit dem letzten Snapshot veraendert hat oder
    neu hinzugekommen ist -- Kandidat fuer den naechsten Schritt (LLM-
    gestuetzter Drift-Check, spaeterer Baustein)."""

    filename: str
    reason: str
    previous_summary: str | None
    current_summary: str


@dataclass(frozen=True)
class DriftDiffResult:
    is_first_run: bool
    candidates: list[DriftCandidate]
    removed_documents: list[str]
    unchanged_count: int


def diff_concept_summaries(
    previous: ConceptSummary | None,
    current: ConceptSummary,
) -> DriftDiffResult:
    """Rein deterministischer Vergleich, kein LLM-Aufruf (siehe Modul-
    Docstring). Vorbild: diff_snapshots() in AI_Project_Reviewer/sync_fis.py.

    Erkennt drei Faelle pro Dokument:
    - neu hinzugekommen seit letztem Snapshot
    - summary-Text hat sich veraendert (Ollama hat beim letzten Lauf etwas
      anderes zusammengefasst -- deutet auf echten Inhaltswechsel hin)
    - mtime der Quelldatei hat sich veraendert, OBWOHL die summary identisch
      blieb (moeglicher Hinweis auf eine Ollama-Zusammenfassung, die zu
      grob ist, um eine kleine, aber relevante Aenderung zu erfassen --
      bewusst trotzdem als Kandidat markiert, nicht verworfen)
    """
    if previous is None:
        return DriftDiffResult(
            is_first_run=True,
            candidates=[
                DriftCandidate(
                    filename=doc.path,
                    reason="Initialer Lauf -- kein Vorzustand vorhanden.",
                    previous_summary=None,
                    current_summary=doc.summary,
                )
                for doc in current.document_summaries
            ],
            removed_documents=[],
            unchanged_count=0,
        )

    previous_by_path = {doc.path: doc.summary for doc in previous.document_summaries}
    current_by_path = {doc.path: doc.summary for doc in current.document_summaries}

    candidates: list[DriftCandidate] = []
    unchanged_count = 0

    for path, current_summary in current_by_path.items():
        previous_summary = previous_by_path.get(path)

        if previous_summary is None:
            candidates.append(
                DriftCandidate(
                    filename=path,
                    reason="Neues Dokument seit letztem Snapshot.",
                    previous_summary=None,
                    current_summary=current_summary,
                )
            )
            continue

        summary_changed = previous_summary != current_summary
        mtime_changed = _mtime_changed(previous, current, path)

        if summary_changed:
            candidates.append(
                DriftCandidate(
                    filename=path,
                    reason="Ollama-Zusammenfassung hat sich seit letztem Snapshot veraendert.",
                    previous_summary=previous_summary,
                    current_summary=current_summary,
                )
            )
        elif mtime_changed:
            candidates.append(
                DriftCandidate(
                    filename=path,
                    reason=(
                        "Datei wurde seit letztem Snapshot veraendert (mtime), "
                        "aber die Ollama-Zusammenfassung blieb identisch -- "
                        "moeglicherweise eine zu grobe Zusammenfassung, bitte "
                        "trotzdem pruefen."
                    ),
                    previous_summary=previous_summary,
                    current_summary=current_summary,
                )
            )
        else:
            unchanged_count += 1

    removed_documents = sorted(set(previous_by_path) - set(current_by_path))

    return DriftDiffResult(
        is_first_run=False,
        candidates=candidates,
        removed_documents=removed_documents,
        unchanged_count=unchanged_count,
    )


def _mtime_changed(previous: ConceptSummary, current: ConceptSummary, doc_path: str) -> bool:
    """Vergleicht source_file_mtimes ueber den Dateinamen (nicht den vollen,
    absoluten Pfad), weil sich der Vault-Root-Praefix theoretisch aendern
    kann (z.B. Repo verschoben), der Dateiname selbst aber stabil bleibt."""
    previous_mtime = _mtime_for_filename(previous.source_file_mtimes, doc_path)
    current_mtime = _mtime_for_filename(current.source_file_mtimes, doc_path)

    if previous_mtime is None or current_mtime is None:
        return False

    return previous_mtime != current_mtime


def _mtime_for_filename(mtimes: dict[str, float], doc_path: str) -> float | None:
    target_name = Path(doc_path).name
    for full_path, mtime in mtimes.items():
        if Path(full_path).name == target_name:
            return mtime
    return None
