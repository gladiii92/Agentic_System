"""
agents/curator_agent/run_drift_check.py

VERSION 2026-08-24, Debug-Ergaenzung: zeigt jetzt reasoning UND
contradiction_summary auch fuer VERWORFENE Findings an (bisher nur fuer
approved-Findings implizit ueber den Writer-Schritt sichtbar). Grund
(siehe Chat-Verlauf): Score 6.20 bei einer eigentlich offensichtlichen
Diskrepanz ("Alle Phasen abgeschlossen" vs. echter Stand) wirkte zu
niedrig -- ohne reasoning/contradiction_summary in der Ausgabe konnte
nicht beurteilt werden, ob das am Judge-Urteil oder an der Score-
Uebersetzung liegt.
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
from agents.curator_agent.line_context_extractor import extract_context, replace_context_in_full_text
from agents.curator_agent.snapshot_store import (
    load_latest_snapshot_with_raw_texts,
    save_snapshot,
)
from agents.evaluator_agent.evaluator import (
    DriftFinding,
    EvaluatorError,
    run_drift_judge,
    score_finding_heuristically,
)
from agents.evaluator_agent.proposal_validation import validate_updated_context
from agents.evaluator_agent.proposal_writer import ProposalWriterError, write_context_proposal
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


def _findings_sorted_descending(findings: list[DriftFinding]) -> list[DriftFinding]:
    return sorted(findings, key=lambda f: f.line_number, reverse=True)


def _handle_single_finding(
    filename: str,
    full_path: Path,
    finding: DriftFinding,
    current_project_concept: str,
    rejection_examples: list[str],
) -> None:
    current_full_text = full_path.read_text(encoding="utf-8")
    total_lines = len(current_full_text.splitlines())

    if finding.line_number < 1 or finding.line_number > total_lines:
        print(
            f"    UEBERSPRUNGEN: Zeile {finding.line_number} liegt ausserhalb des "
            f"aktuellen Dokuments (1-{total_lines})."
        )
        return

    context = extract_context(current_full_text, finding.line_number)

    try:
        written = write_context_proposal(
            filename=filename,
            target_line_number=finding.line_number,
            numbered_context_text=context.context_text,
            contradiction_summary=finding.contradiction_summary,
            suggested_update=finding.suggested_update,
            current_project_concept=current_project_concept,
            rejection_examples=rejection_examples,
        )
    except ProposalWriterError as exc:
        print(f"    FEHLER beim Erzeugen des Vorschlags fuer Zeile {finding.line_number}: {exc}")
        return

    validation = validate_updated_context(context.context_text_plain, written.updated_context_text)
    if not validation.passed:
        print(f"    AUTOMATISCH VERWORFEN fuer Zeile {finding.line_number}:")
        for failure in validation.failures:
            print(f"      - {failure}")
        return

    updated_full_text = replace_context_in_full_text(current_full_text, context, written.updated_context_text)

    print("\n" + "=" * 70)
    print(f"VORSCHAU FUER: {filename}, Zeile {finding.line_number} (Kontext {context.context_start_line}-{context.context_end_line})")
    print("=" * 70)
    print(f"Aenderungs-Zusammenfassung: {written.change_summary}\n")

    if not has_actual_changes(current_full_text, updated_full_text):
        print("Kein tatsaechlicher Unterschied im vorgeschlagenen Text -- wird uebersprungen.")
        return

    diff_text = build_unified_diff(current_full_text, updated_full_text, filename)
    print(diff_text)
    print()

    answer = input(
        f"Diese Aenderung an Zeile {finding.line_number} JETZT schreiben? (ja/nein): "
    ).strip().lower()

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
            contradiction_summary=finding.contradiction_summary,
            suggested_update=finding.suggested_update,
            proposed_text=written.updated_context_text,
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
    all_findings_by_candidate: dict[str, list[DriftFinding]] = {}
    any_judge_error = False

    for candidate in passed_candidates:
        print(f"\n  Pruefe: {candidate.filename} ...")
        recent_worklogs = _recent_worklog_summaries(current_summary, candidate.filename)
        full_text = current_raw_texts.get(candidate.filename, "")

        try:
            findings = run_drift_judge(
                filename=candidate.filename,
                full_document_text=full_text,
                current_project_concept=current_summary.concept_text,
                recent_worklog_summaries=recent_worklogs,
            )
        except EvaluatorError as exc:
            print(f"    FEHLER beim Judge-Aufruf: {exc}")
            any_judge_error = True
            continue

        print(f"    -> {len(findings)} Finding(s) gefunden.")
        approved_findings = []
        for finding in findings:
            scored = score_finding_heuristically(finding)
            print(f"\n    Zeile {finding.line_number} ({finding.severity}):")
            print(f"      Begruendung: {finding.reasoning}")
            print(f"      Widerspruch: {finding.contradiction_summary}")
            print(f"      Vorschlag: {finding.suggested_update}")
            print(f"      Score: {scored.weighted_score:.2f}, approved={scored.approved}")
            if scored.approved:
                approved_findings.append(finding)
            else:
                print(f"      Verworfen: {scored.rejection_reason}")

        if approved_findings:
            all_findings_by_candidate[candidate.filename] = approved_findings

    if any_judge_error:
        print("\nWARNUNG: Mindestens ein Judge-Aufruf ist fehlgeschlagen (Snapshot wird trotzdem gespeichert).")

    save_snapshot(CURATOR_DATA_ROOT, TARGET_PROJECT_NAME, current_summary)

    if not all_findings_by_candidate:
        print("\nKeine freigegebenen Findings.")
        return

    print("\nSchritt 6/6: Fuer jedes Finding einzeln -- Kontext extrahieren, Human-in-the-Loop...")
    rejections = load_rejections(REJECTION_HISTORY_ROOT, AGENT_NAME)
    rejection_examples = format_for_prompt(rejections)

    for filename, findings in all_findings_by_candidate.items():
        full_path = _full_path_for_filename(current_summary.source_file_mtimes, filename)
        if full_path is None:
            print(f"ABBRUCH fuer {filename}: Pfad nicht auffindbar.")
            continue

        findings_desc = _findings_sorted_descending(findings)
        print(f"\n{filename}: {len(findings_desc)} Finding(s) werden von unten nach oben verarbeitet.")

        for finding in findings_desc:
            _handle_single_finding(
                filename=filename,
                full_path=full_path,
                finding=finding,
                current_project_concept=current_summary.concept_text,
                rejection_examples=rejection_examples,
            )


if __name__ == "__main__":
    run()
