"""
agents/curator_agent/drift_diff.py

Dritter Baustein des Curator-Agenten (Phase 1), Schicht 1 der Evaluator-
Kaskade (siehe evaluator_agent/README.md fuer die Gesamt-Uebersicht der
Kaskade). Zweck: rein deterministischer Vorab-Check zwischen zwei
ConceptSummary-Staenden (vorheriger Snapshot vs. aktueller Lauf), ANALOG
zum Muster aus AI_Project_Reviewer/sync_fis.py (diff_snapshots-Funktion).

WICHTIG -- Ausloeser-Logik geaendert am 2026-08-23 (siehe Chat-Verlauf,
Testlauf mit 13 Kandidaten, davon 11 reine Ollama-Formulierungsvarianz):
Frueher loeste JEDE Text-Ungleichheit zwischen previous_summary und
current_summary einen Kandidaten aus. Das war zu grosszuegig, weil Ollama
bei jedem Lauf leicht anders formuliert, OHNE dass sich der Inhalt
aendert (siehe arXiv-Recherche zu "semantic drift" bei gleichbleibender
Bedeutung, Chat-Verlauf). NEU: alleiniger deterministischer Ausloeser ist
die Datei-mtime (Best-Practice-Empfehlung: "cheap deterministic tests
first", siehe Recherche 2026-08-23). Der Text-Gleichheits-Status wird
weiterhin mitgefuehrt (summary_text_changed), aber NUR als Information
fuer die naechste Schicht (embedding_filter.py), nicht mehr als eigener
Ausloeser.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agents.curator_agent.concept_loader import ConceptSummary


@dataclass(frozen=True)
class DriftCandidate:
    """Ein Dokument, dessen Quelldatei sich seit dem letzten Snapshot
    nachweislich veraendert hat (mtime) oder das neu hinzugekommen ist --
    Kandidat fuer Schicht 2 (Embedding-Aehnlichkeit, embedding_filter.py)."""

    filename: str
    reason: str
    previous_summary: str | None
    current_summary: str
    summary_text_changed: bool


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
    """Rein deterministischer Vergleich, kein LLM-Aufruf. Ausloeser fuer
    einen Kandidaten ist AUSSCHLIESSLICH: neues Dokument ODER veraenderte
    mtime der Quelldatei (siehe Modul-Docstring, Entscheidung 2026-08-23).
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
                    summary_text_changed=True,
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
                    summary_text_changed=True,
                )
            )
            continue

        mtime_changed = _mtime_changed(previous, current, path)
        summary_text_changed = previous_summary != current_summary

        if mtime_changed:
            candidates.append(
                DriftCandidate(
                    filename=path,
                    reason="Quelldatei wurde seit letztem Snapshot veraendert (mtime).",
                    previous_summary=previous_summary,
                    current_summary=current_summary,
                    summary_text_changed=summary_text_changed,
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
