"""
agents/curator_agent/run_drift_check.py

Orchestrator, FINALE Version fuer Phase-1-MVP (2026-08-24, Fix 4 --
Abschnitts-basiertes Schreiben statt Ganze-Datei-Umschreibung). Aenderung
gegenueber der vorherigen Version, siehe Chat-Verlauf:

    6a. Abschnitt lokalisieren (section_locator.py) -- WELCHER Teil der
        Datei ist tatsaechlich betroffen?
    6b. NUR diesen Abschnitt an Ollama schicken (proposal_writer.py v2)
    6c. Deterministische Validierung DES ERGEBNISSES (proposal_validation.py)
        -- bei Fehlschlag: automatisch verwerfen, NICHT anzeigen
    6d. Volltext programmatisch neu zusammensetzen (section_locator.replace_section)
        -- der Rest der Datei bleibt garantiert byte-identisch
    6e. Diff anzeigen, Human-in-the-Loop-Bestaetigung, Schreiben/Ablehnen

Diese Kette macht eine Beschaedigung unbeteiligter Abschnitte STRUKTURELL
unmoeglich -- unabhaengig davon, was Ollama im Einzelfall tut.
"""

from __future__ import annotations

from pathlib import Path

from agents.curator_agent.concept_loader import (
    ConceptSummaryLoadError,
    refresh_and_load,
)
from agents.curator_agent.diff_presenter import build_unified_diff, has_actual_changes
from agents.curator_agent.drift_diff import diff_concept_summaries
from agents.curator_agent.embedding_filter_chunked import filter_candidates
from agents.curator_agent.section_locator import (
    find_most_relevant_section,
    replace_section,
    split_into_sections,
)
from agents.curator_agent.snapshot_store import (
    load_latest_snapshot_with_raw_texts,
    save_snapshot,
)
from agents.evaluator_agent.evaluator import (
    EvaluatorError,
    run_drift_judge,
    score_drift_judgment_heuristically,
)
from agents.evaluator_agent.proposal_validation import validate_updated_section
from agents.evaluator_agent.proposal_writer import ProposalWriterError, write_section_proposal
from agents.evaluator_agent.rejection_history import (
    format_for_prompt,
    load_rejections,
    record_rejection,
)

AI_PROJECT_REVIEWER_REPO_PATH = Path(r"G:\DAVID\Desktop\GitHub\AI_Project_Reviewer")
CURATOR_DATA_ROOT = Path(r"G:\DAVID\Desktop\GitHub\Agentic_System\data")
REJECTION_HISTORY_ROOT = Path(r"G:\DAVID\Desktop\GitHub\Agentic_System\data\rejection_history")
TARGET_PROJECT_NAME = "AI_Project_Reviewer"
AGENT_NAME = "curator_agent"


def _read_current_raw_texts(source_file_mtimes: dict[str, float]) -> dict[str, str]:
    raw_texts: dict[str, str] = {}
    for full_path in source_file_mtimes:
        filename = Path(full_path).name
        try:
            raw_texts[filename] = Path(full_path).read_text(encoding="utf-8")
        except OSError as exc:
            raw_texts[filename] = f"__READ_ERROR__: {exc}"
    return raw_texts


def _full_path_for_filename(source_file_mtimes: dict[str, float], filename: str) -> Path | None:
    for full_path in source_file_mtimes:
        if Path(full_path).name == filename:
            return Path(full_path)
    return None


def _recent_worklog_summaries(current_summary, exclude_filename: str) -> str:
    parts = []
    for doc in current_summary.document_summaries:
        if doc.path == exclude_filename:
            continue
        if "worklog" in doc.path.lower():
            parts.append(f"- {doc.path}: {doc.summary}")
    return "\n".join(parts)


def _handle_human_in_the_loop(
    filename: str,
    original_full_text: str,
    updated_full_text: str,
    change_summary: str,
    contradiction_summary: str,
    suggested_update: str,
    full_path: Path,
) -> None:
    print("\n" + "=" * 70)
    print(f"VORSCHAU FUER: {filename}")
    print("=" * 70)
    print(f"Aenderungs-Zusammenfassung: {change_summary}\n")

    if not has_actual_changes(original_full_text, updated_full_text):
        print("Kein tatsaechlicher Unterschied im vorgeschlagenen Text -- wird uebersprungen.")
        return

    diff_text = build_unified_diff(original_full_text, updated_full_text, filename)
    print(diff_text)
    print()

    answer = input(f"Diesen Vorschlag fuer {filename} JETZT schreiben? (ja/nein): ").strip().lower()

    if answer in ("ja", "j", "yes", "y"):
        full_path.write_text(updated_full_text, encoding="utf-8")
        print(f"-> Geschrieben: {full_path}")
    else:
        reason = input("Kurzer Grund fuer die Ablehnung (Pflichtfeld): ").strip()
        while not reason:
            reason = input("Grund darf nicht leer sein: ").strip()
        record_rejection(
            rejection_history_root=REJECTION_HISTORY_ROOT,
            agent_name=AGENT_NAME,
            filename=filename,
            contradiction_summary=contradiction_summary,
            suggested_update=suggested_update,
            proposed_text=updated_full_text,
            rejection_reason=reason,
        )
        print("-> Abgelehnt. In Ablehnungs-Historie gespeichert fuer kuenftige Prompts.")


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
        print(f"ABBRUCH (Snapshot NICHT gespeichert): {exc}")
        return

    print(f"  -> {len(current_summary.document_summaries)} Dokument(e) zusammengefasst.")
    current_raw_texts = _read_current_raw_texts(current_summary.source_file_mtimes)

    print("Schritt 2/6: Vorherigen Snapshot (inkl. Rohtext-Historie) laden...")
    previous_result = load_latest_snapshot_with_raw_texts(CURATOR_DATA_ROOT, TARGET_PROJECT_NAME)
    if previous_result is None:
        previous_summary, previous_raw_texts = None, {}
        print("  -> Kein vorheriger Snapshot gefunden (erster Lauf fuer dieses Projekt).")
    else:
        previous_summary, previous_raw_texts = previous_result
        print(f"  -> Vorheriger Snapshot vom {previous_summary.generated_at} geladen.")

    print("Schritt 3/6: Schicht 1 -- deterministischer mtime-Diff...")
    diff_result = diff_concept_summaries(previous=previous_summary, current=current_summary)
    print(f"  -> {len(diff_result.candidates)} Kandidat(en) aus Schicht 1 (mtime veraendert/neu).")

    if diff_result.is_first_run:
        save_snapshot(CURATOR_DATA_ROOT, TARGET_PROJECT_NAME, current_summary)
        print(f"\nErster Lauf. {len(diff_result.candidates)} Dokument(e) als Baseline gespeichert.")
        return

    if not diff_result.candidates:
        save_snapshot(CURATOR_DATA_ROOT, TARGET_PROJECT_NAME, current_summary)
        print("\nKeine Aenderungen seit letztem Snapshot erkannt. Snapshot aktualisiert. Fertig.")
        return

    print("Schritt 4/6: Schicht 2 -- Rohtext-Embedding-Aehnlichkeits-Filter...")
    try:
        embedding_results = filter_candidates(
            diff_result.candidates,
            previous_raw_texts=previous_raw_texts,
            current_raw_texts=current_raw_texts,
        )
    except Exception as exc:
        print(f"ABBRUCH in Schicht 2 (Snapshot NICHT gespeichert): {exc}")
        return

    passed_candidates = [r.candidate for r in embedding_results if r.passed]

    for r in embedding_results:
        status = "WEITERGEREICHT" if r.passed else "VERWORFEN"
        print(f"  - {r.candidate.filename}: {status} ({r.reason})")

    if not passed_candidates:
        save_snapshot(CURATOR_DATA_ROOT, TARGET_PROJECT_NAME, current_summary)
        print("\nAlle Kandidaten von Schicht 2 verworfen. Snapshot aktualisiert. Fertig.")
        return

    print(f"\nSchritt 5/6: Schicht 3 -- LLM-Judge fuer {len(passed_candidates)} Kandidat(en)...")
    approved_proposals = []
    any_judge_error = False

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
            any_judge_error = True
            continue

        print(f"    has_drift={judgment.has_drift}, severity={judgment.severity}")
        print(f"    Begruendung: {judgment.reasoning}")

        scored = score_drift_judgment_heuristically(judgment)
        print(f"    Gewichteter Score: {scored.weighted_score:.2f} -- approved={scored.approved}")

        if scored.approved and judgment.has_drift:
            approved_proposals.append((candidate, judgment, scored))
        elif not scored.approved:
            print(f"    Verworfen vom Evaluator: {scored.rejection_reason}")

    if any_judge_error:
        print("\nWARNUNG: Mindestens ein Judge-Aufruf ist fehlgeschlagen (Snapshot wird trotzdem gespeichert).")

    save_snapshot(CURATOR_DATA_ROOT, TARGET_PROJECT_NAME, current_summary)

    if not approved_proposals:
        print("\nKeine freigegebenen Vorschlaege.")
        return

    print("\nSchritt 6/6: Abschnitt lokalisieren, gezielt umschreiben, validieren, Human-in-the-Loop...")
    rejections = load_rejections(REJECTION_HISTORY_ROOT, AGENT_NAME)
    rejection_examples = format_for_prompt(rejections)

    for candidate, judgment, scored in approved_proposals:
        original_full_text = current_raw_texts.get(candidate.filename)
        full_path = _full_path_for_filename(current_summary.source_file_mtimes, candidate.filename)

        if original_full_text is None or full_path is None:
            print(f"ABBRUCH fuer {candidate.filename}: Originaltext/Pfad nicht auffindbar.")
            continue

        sections = split_into_sections(original_full_text)
        target_section = find_most_relevant_section(
            sections, judgment.contradiction_summary, judgment.suggested_update
        )
        print(f"\n  Lokalisierter Abschnitt fuer {candidate.filename}: '{target_section.heading}'")

        try:
            written = write_section_proposal(
                filename=candidate.filename,
                section_heading=target_section.heading,
                section_text=target_section.text,
                contradiction_summary=judgment.contradiction_summary,
                suggested_update=judgment.suggested_update,
                current_project_concept=current_summary.concept_text,
                rejection_examples=rejection_examples,
            )
        except ProposalWriterError as exc:
            print(f"FEHLER beim Erzeugen des Abschnitts-Vorschlags fuer {candidate.filename}: {exc}")
            continue

        validation = validate_updated_section(target_section.text, written.updated_section_text)
        if not validation.passed:
            print(f"  AUTOMATISCH VERWORFEN (deterministische Validierung fehlgeschlagen):")
            for failure in validation.failures:
                print(f"    - {failure}")
            print("  Vorschlag wird NICHT angezeigt. Bitte spaeter erneut versuchen oder Prompt anpassen.")
            continue

        updated_full_text = replace_section(original_full_text, target_section, written.updated_section_text)

        _handle_human_in_the_loop(
            filename=candidate.filename,
            original_full_text=original_full_text,
            updated_full_text=updated_full_text,
            change_summary=written.change_summary,
            contradiction_summary=judgment.contradiction_summary,
            suggested_update=judgment.suggested_update,
            full_path=full_path,
        )


if __name__ == "__main__":
    run()
