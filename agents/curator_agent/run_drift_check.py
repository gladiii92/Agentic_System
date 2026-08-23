"""
agents/curator_agent/run_drift_check.py

Vierter Baustein / Orchestrator fuer Phase 1 (Curator-Agent, Teil 1).
Fuehrt EINEN kompletten manuellen Curator-Durchlauf aus:

    1. Frischen concept_summary-Lauf ueber AI_Project_Reviewer anstossen
       und laden (concept_loader.py)
    2. Vorherigen eigenen Snapshot laden, falls vorhanden (snapshot_store.py)
    3. Deterministischen Diff berechnen -- WELCHE Dokumente sind
       Drift-Kandidaten? (drift_diff.py)
    4. Aktuellen Stand als neuen Snapshot sichern (snapshot_store.py)
    5. Ergebnis in Klartext ausgeben (KEIN LLM-Urteil, KEIN Schreiben ins
       FIS-Vault -- das sind spaetere Bausteine, siehe Chat-Verlauf)

Bewusst als eigenstaendiges, direkt ausfuehrbares Skript (kein Import in
anderen Modulen vorausgesetzt), damit du es einfach manuell anstossen
kannst (siehe Entscheidung "rein manueller Trigger", Chat-Verlauf
2026-08-23). Spaetere Automatisierung (Cron/Task Scheduler) kann dieses
Skript unveraendert per `python -m agents.curator_agent.run_drift_check`
aufrufen.
"""

from __future__ import annotations

from pathlib import Path

from agents.curator_agent.concept_loader import (
    ConceptSummaryLoadError,
    refresh_and_load,
)
from agents.curator_agent.drift_diff import diff_concept_summaries
from agents.curator_agent.snapshot_store import load_latest_snapshot, save_snapshot

# TODO gemeinsam anpassen, falls Pfade abweichen (siehe config.py im Root
# von Agentic_System -- perspektivisch sollten diese Konstanten von dort
# importiert werden statt hier hart codiert zu sein; fuer den ersten
# End-to-End-Test bewusst noch lokal gehalten, siehe Chat-Verlauf).
AI_PROJECT_REVIEWER_REPO_PATH = Path(r"G:\DAVID\Desktop\GitHub\AI_Project_Reviewer")
CURATOR_DATA_ROOT = Path(r"G:\DAVID\Desktop\GitHub\Agentic_System\data")
TARGET_PROJECT_NAME = "AI_Project_Reviewer"


def run() -> None:
    print(f"Starte Curator-Durchlauf fuer Projekt: {TARGET_PROJECT_NAME}")
    print("Schritt 1/4: Frischer concept_summary-Lauf (kann ca. 1 Minute dauern)...")

    try:
        current_summary = refresh_and_load(
            ai_project_reviewer_repo_path=AI_PROJECT_REVIEWER_REPO_PATH,
            target_project_path=AI_PROJECT_REVIEWER_REPO_PATH,
            project_name=TARGET_PROJECT_NAME,
        )
    except ConceptSummaryLoadError as exc:
        print(f"ABBRUCH: {exc}")
        return

    print(f"  -> {len(current_summary.document_summaries)} Dokument(e) zusammengefasst.")

    print("Schritt 2/4: Vorherigen Snapshot laden...")
    previous_summary = load_latest_snapshot(CURATOR_DATA_ROOT, TARGET_PROJECT_NAME)
    if previous_summary is None:
        print("  -> Kein vorheriger Snapshot gefunden (erster Lauf fuer dieses Projekt).")
    else:
        print(f"  -> Vorheriger Snapshot vom {previous_summary.generated_at} geladen.")

    print("Schritt 3/4: Deterministischen Drift-Diff berechnen...")
    diff_result = diff_concept_summaries(previous=previous_summary, current=current_summary)

    print("Schritt 4/4: Aktuellen Stand als neuen Snapshot sichern...")
    saved_path = save_snapshot(CURATOR_DATA_ROOT, TARGET_PROJECT_NAME, current_summary)
    print(f"  -> Gespeichert unter: {saved_path}")

    print()
    print("=" * 70)
    print("ERGEBNIS (rein deterministisch, noch KEIN LLM-Urteil)")
    print("=" * 70)

    if diff_result.is_first_run:
        print(
            f"Erster Lauf. {len(diff_result.candidates)} Dokument(e) als Baseline "
            f"gespeichert, noch kein Vergleich moeglich."
        )
        return

    print(f"Unveraendert: {diff_result.unchanged_count} Dokument(e)")
    print(f"Drift-Kandidaten: {len(diff_result.candidates)} Dokument(e)")
    for candidate in diff_result.candidates:
        print(f"\n  - {candidate.filename}")
        print(f"    Grund: {candidate.reason}")

    if diff_result.removed_documents:
        print(f"\nEntfernte Dokumente seit letztem Snapshot: {diff_result.removed_documents}")

    if not diff_result.candidates and not diff_result.removed_documents:
        print("\nKeine Aenderungen seit letztem Snapshot erkannt.")


if __name__ == "__main__":
    run()
