"""
agents/curator_agent/run_drift_check.py

Orchestrator fuer Phase 1 (Curator-Agent + Evaluator-Agent, komplette
Kaskade). Fuehrt EINEN kompletten manuellen Durchlauf aus:

    1. Frischen concept_summary-Lauf ueber AI_Project_Reviewer anstossen
       und laden (concept_loader.py)
    2. Vorherigen eigenen Snapshot laden, falls vorhanden (snapshot_store.py)
    3. Schicht 1 -- deterministischer mtime-Diff (drift_diff.py)
    4. Schicht 2 -- Embedding-Aehnlichkeits-Filter (embedding_filter.py)
    5. Schicht 3 -- LLM-Judge pro durchgelassenem Kandidaten (evaluator.py)
    6. Vier-Kriterien-Scoring pro Judgment, NUR approved-Vorschlaege werden
       dir angezeigt (evaluator.py score_drift_judgment_heuristically)
    7. Aktuellen Stand als neuen Snapshot sichern (snapshot_store.py)

WICHTIG: Dieses Skript SCHREIBT NICHTS ins FIS-Vault. Es zeigt dir nur
an, was der Evaluator freigegeben hat -- das tatsaechliche Schreiben der
ROADMAP.md o.ae. ist ein spaeterer Baustein (Human-in-the-Loop-
Bestaetigung + Schreibvorgang), bewusst noch nicht Teil dieser Phase.
"""

from __future__ import annotations

from pathlib import Path

from agents.curator_agent.concept_loader import (
    ConceptSummaryLoadError,
    refresh_and_load,
)
from agents.curator_agent.drift_diff import diff_concept_summaries
from agents.curator_agent.embedding_filter import filter_candidates
from agents.curator_agent.snapshot_store import load_latest_snapshot, save_snapshot
from agents.evaluator_agent.evaluator import (
    EvaluatorError,
    run_drift_judge,
    score_drift_judgment_heuristically,
)

AI_PROJECT_REVIEWER_REPO_PATH = Path(r"G:\DAVID\Desktop\GitHub\AI_Project_Reviewer")
CURATOR_DATA_ROOT = Path(r"G:\DAVID\Desktop\GitHub\Agentic_System\data")
TARGET_PROJECT_NAME = "AI_Project_Reviewer"


def _recent_worklog_summaries(current_summary, exclude_filename: str) -> str:
    """Baut den Zusatzkontext fuer den Judge-Prompt: Text aus allen
    Worklog-Dokumenten AUSSER dem aktuell geprueften Dokument selbst.
    Bewusst simple Heuristik ueber den Dateinamen ("Worklog" im Namen) --
    reicht fuer Phase 1, kann spaeter verfeinert werden (z.B. echte
    zeitliche Sortierung statt Namens-Heuristik)."""
    parts = []
    for doc in current_summary.document_summaries:
        if doc.path == exclude_filename:
            continue
        if "worklog" in doc.path.lower():
            parts.append(f"- {doc.path}: {doc.summary}")
    return "\n".join(parts)


def run() -> None:
    print(f"Starte Curator+Evaluator-Durchlauf fuer Projekt: {TARGET_PROJECT_NAME}")
    print("Schritt 1/6: Frischer concept_summary-Lauf (kann ca. 1 Minute dauern)...")

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

    print("Schritt 2/6: Vorherigen Snapshot laden...")
    previous_summary = load_latest_snapshot(CURATOR_DATA_ROOT, TARGET_PROJECT_NAME)
    if previous_summary is None:
        print("  -> Kein vorheriger Snapshot gefunden (erster Lauf fuer dieses Projekt).")
    else:
        print(f"  -> Vorheriger Snapshot vom {previous_summary.generated_at} geladen.")

    print("Schritt 3/6: Schicht 1 -- deterministischer mtime-Diff...")
    diff_result = diff_concept_summaries(previous=previous_summary, current=current_summary)

    saved_path = save_snapshot(CURATOR_DATA_ROOT, TARGET_PROJECT_NAME, current_summary)
    print(f"  -> Snapshot gespeichert unter: {saved_path}")

    if diff_result.is_first_run:
        print(
            f"\nErster Lauf. {len(diff_result.candidates)} Dokument(e) als Baseline "
            f"gespeichert, noch kein Vergleich moeglich."
        )
        return

    print(f"  -> {len(diff_result.candidates)} Kandidat(en) aus Schicht 1 (mtime veraendert/neu).")

    if not diff_result.candidates:
        print("\nKeine Aenderungen seit letztem Snapshot erkannt. Fertig.")
        return

    print("Schritt 4/6: Schicht 2 -- Embedding-Aehnlichkeits-Filter...")
    embedding_results = filter_candidates(diff_result.candidates)
    passed_candidates = [r.candidate for r in embedding_results if r.passed]

    for r in embedding_results:
        status = "WEITERGEREICHT" if r.passed else "VERWORFEN"
        print(f"  - {r.candidate.filename}: {status} ({r.reason})")

    if not passed_candidates:
        print("\nAlle Kandidaten wurden von Schicht 2 verworfen (reine Formulierungsvarianz). Fertig.")
        return

    print(f"\nSchritt 5/6: Schicht 3 -- LLM-Judge fuer {len(passed_candidates)} Kandidat(en)...")
    approved_proposals = []

    for candidate in passed_candidates:
        print(f"\n  Pruefe: {candidate.filename} ...")
        recent_worklogs = _recent_worklog_summaries(current_summary, candidate.filename)

        try:
            judgment = run_drift_judge(
                filename=candidate.filename,
                document_summary=candidate.current_summary,
                current_project_concept=current_summary.concept_text,
                recent_worklog_summaries=recent_worklogs,
            )
        except EvaluatorError as exc:
            print(f"    FEHLER beim Judge-Aufruf: {exc}")
            continue

        print(f"    has_drift={judgment.has_drift}, severity={judgment.severity}")
        print(f"    Begruendung: {judgment.reasoning}")

        print("Schritt 6/6: Vier-Kriterien-Scoring...")
        scored = score_drift_judgment_heuristically(judgment)
        print(f"    Gewichteter Score: {scored.weighted_score:.2f} -- approved={scored.approved}")

        if scored.approved and judgment.has_drift:
            approved_proposals.append((judgment, scored))
        elif not scored.approved:
            print(f"    Verworfen vom Evaluator: {scored.rejection_reason}")

    print()
    print("=" * 70)
    print("ERGEBNIS -- vom Evaluator freigegebene Drift-Vorschlaege")
    print("=" * 70)

    if not approved_proposals:
        print("Keine freigegebenen Vorschlaege. Entweder kein echter Drift erkannt,")
        print("oder alle Kandidaten wurden vom Evaluator als nicht ausreichend bewertet.")
        return

    for judgment, scored in approved_proposals:
        print(f"\n--- {judgment.filename} (Score {scored.weighted_score:.2f}, Severity {judgment.severity}) ---")
        print(f"Widerspruch: {judgment.contradiction_summary}")
        print(f"Vorschlag: {judgment.suggested_update}")


if __name__ == "__main__":
    run()
