"""
agents/curator_agent/run_drift_check.py

VERSION 2026-08-26b -- PATCH-WRITER VOLLKONTEXT-ERGAENZUNG (siehe Chat-
Verlauf). Aufbauend auf VERSION 2026-08-26 (Judge-Vollkontext-Fix).

Aenderung gegenueber der Version 2026-08-26 (Vormittag):
- _handle_hunk() reicht jetzt full_document_text auch an write_patch()
  weiter (bisher nur an run_drift_judge()). Grund (realer Testfall
  ROADMAP.md, 2026-08-26): der Patch-Writer kannte bisher nur den
  kleinen Hunk und hat dadurch die FALSCHE Zeile korrigiert (die
  Tabellenzeile zu Phase 8 verstuemmelt, statt sie korrekt zu berichtigen
  oder den eigentlich falschen Satz zu aendern) -- siehe
  patch_writer_prompt.py-Docstring fuer die volle Begruendung.

Alle anderen Schritte (1-8) sind UNVERAENDERT gegenueber der Version vom
2026-08-26 Vormittag.
"""

from __future__ import annotations

from pathlib import Path

from agents.curator_agent.concept_loader import (
    ConceptSummaryLoadError,
    refresh_and_load,
)
from agents.curator_agent.diff_presenter import build_unified_diff
from agents.curator_agent.drift_diff import diff_concept_summaries
from agents.curator_agent.snapshot_store import (
    load_latest_snapshot_with_raw_texts,
    save_snapshot,
)
from agents.evaluator_agent.evaluator import (
    EvaluatorError,
    run_drift_judge,
    score_judgment_heuristically,
)
from agents.evaluator_agent.patch_writer import PatchWriterError, write_patch
from agents.evaluator_agent.rejection_history import (
    format_for_prompt,
    load_rejections,
    record_rejection,
)
from patching.diff_hunks import compute_diff_hunks, render_hunk_for_prompt
from patching.patch_applier import apply_patch
from patching.patch_validator import validate_patch

AI_PROJECT_REVIEWER_REPO_PATH = Path(r"G:\DAVID\Desktop\GitHub\AI_Project_Reviewer")
CURATOR_DATA_ROOT = Path(r"G:\DAVID\Desktop\GitHub\Agentic_System\data")
REJECTION_HISTORY_ROOT = Path(r"G:\DAVID\Desktop\GitHub\Agentic_System\data\rejection_history")
TARGET_PROJECT_NAME = "AI_Project_Reviewer"
AGENT_NAME = "curator_agent"

# Sicherheitsnetz gegen sehr lange Dokumente im Vollkontext-Prompt (siehe
# evaluator.py DEFAULT_NUM_CTX-Kommentar fuer die Kontextfenster-Begruendung).
MAX_FULL_DOCUMENT_CHARS = 20_000


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


def _other_document_summaries(current_summary, exclude_filename: str) -> str:
    """Sammelt die Ollama-Zusammenfassungen ALLER anderen Dokumente im
    Projekt, unabhaengig vom Dateinamen (kein "worklog"-Filter mehr --
    siehe Chat-Verlauf 2026-08-26 fuer die Begruendung der
    Generalisierung)."""
    parts = []
    for doc in current_summary.document_summaries:
        if doc.path == exclude_filename:
            continue
        parts.append(f"- {doc.path}: {doc.summary}")
    return "\n".join(parts)


def _clip_document_text(text: str, max_chars: int = MAX_FULL_DOCUMENT_CHARS) -> str:
    """Einfaches Sicherheitsnetz gegen sehr lange Dokumente. Kein
    Chunking, nur harte Kuerzung mit sichtbarem Hinweis, damit Judge/
    Patch-Writer wissen, dass der Text unvollstaendig ist."""
    if len(text) <= max_chars:
        return text
    return (
        text[:max_chars]
        + f"\n\n[... Dokument gekuerzt, {len(text) - max_chars} weitere Zeichen nicht angezeigt ...]"
    )


def _handle_hunk(
    filename: str,
    full_path: Path,
    hunk,
    current_project_concept: str,
    other_document_summaries: str,
    full_document_text: str,
    rejection_examples: list[str],
) -> None:
    hunk_text = render_hunk_for_prompt(hunk)
    clipped_full_text = _clip_document_text(full_document_text)

    try:
        judgment = run_drift_judge(
            filename=filename,
            hunk_diff_text=hunk_text,
            current_project_concept=current_project_concept,
            recent_worklog_summaries=other_document_summaries,
            full_document_text=clipped_full_text,
        )
    except EvaluatorError as exc:
        print(f"  FEHLER beim Judge-Aufruf fuer diesen Hunk: {exc}")
        return

    print(f"  is_meaningful={judgment.is_meaningful}, is_supported={judgment.is_supported}, severity={judgment.severity}")
    print(f"  Begruendung: {judgment.reasoning}")

    if not judgment.is_meaningful:
        print("  -> Trivial/nicht bedeutsam, wird uebersprungen.")
        return

    if judgment.is_supported:
        print("  -> Kein Widerspruch zum Projektstand erkannt, wird uebersprungen.")
        return

    scored = score_judgment_heuristically(judgment)
    print(f"  Score: {scored.weighted_score:.2f}, approved={scored.approved}")

    if not scored.approved:
        print(f"  Verworfen vom Evaluator: {scored.rejection_reason}")
        return

    try:
        proposed_patch = write_patch(
            filename=filename,
            contradiction_summary=judgment.contradiction_summary,
            hunk_diff_text=hunk_text,
            current_project_concept=current_project_concept,
            full_document_text=clipped_full_text,
            rejection_examples=rejection_examples,
        )
    except PatchWriterError as exc:
        print(f"  FEHLER beim Erzeugen des Patches: {exc}")
        return

    current_full_text = full_path.read_text(encoding="utf-8")
    validation = validate_patch(proposed_patch, current_full_text)

    if not validation.passed:
        print("  AUTOMATISCH VERWORFEN (Patch-Validierung fehlgeschlagen):")
        for failure in validation.failures:
            print(f"    - {failure}")
        return

    validated_patch = validation.validated_patch

    result = apply_patch(current_full_text, validated_patch)
    if not result.success:
        print(f"  FEHLER bei der Patch-Anwendung: {result.error_message}")
        return

    print("\n" + "=" * 70)
    print(f"VORSCHAU FUER: {filename}")
    print("=" * 70)
    print(f"Aenderungs-Zusammenfassung: {validated_patch.change_summary}\n")

    diff_text = build_unified_diff(current_full_text, result.updated_full_text, filename)
    print(diff_text)
    print()

    answer = input("Diesen Patch JETZT schreiben? (ja/nein): ").strip().lower()

    if answer in ("ja", "j", "yes", "y"):
        full_path.write_text(result.updated_full_text, encoding="utf-8")
        print(f"-> Geschrieben: {full_path}")
    else:
        reason = input("Kurzer Grund fuer die Ablehnung (Pflichtfeld): ").strip()
        while not reason:
            reason = input("Grund darf nicht leer sein: ").strip()
        record_rejection(
            rejection_history_root=REJECTION_HISTORY_ROOT,
            agent_name=AGENT_NAME,
            filename=filename,
            contradiction_summary=judgment.contradiction_summary,
            suggested_update=validated_patch.replacement_text,
            proposed_text=validated_patch.replacement_text,
            rejection_reason=reason,
        )
        print("-> Abgelehnt. In Ablehnungs-Historie gespeichert fuer kuenftige Prompts.")


def run() -> None:
    print(f"Starte Curator+Evaluator-Durchlauf fuer Projekt: {TARGET_PROJECT_NAME}")
    print("Schritt 1/5: Frischer concept_summary-Lauf (kann ca. 1 Minute dauern)...")

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

    print("Schritt 2/5: Vorherigen Snapshot (inkl. Rohtext-Historie) laden...")
    previous_result = load_latest_snapshot_with_raw_texts(CURATOR_DATA_ROOT, TARGET_PROJECT_NAME)
    if previous_result is None:
        previous_summary, previous_raw_texts = None, {}
        print("  -> Kein vorheriger Snapshot gefunden (erster Lauf fuer dieses Projekt).")
    else:
        previous_summary, previous_raw_texts = previous_result
        print(f"  -> Vorheriger Snapshot vom {previous_summary.generated_at} geladen.")

    print("Schritt 3/5: Schicht 1 -- deterministischer mtime-Diff...")
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

    print("Schritt 4/5: Deterministische Diff-Hunks pro geaenderter Datei berechnen...")
    rejections = load_rejections(REJECTION_HISTORY_ROOT, AGENT_NAME)
    rejection_examples = format_for_prompt(rejections)

    for candidate in diff_result.candidates:
        if candidate.previous_summary is None:
            print(f"\n{candidate.filename}: neues Dokument, kein Vorzustand fuer Hunk-Diff -- wird uebersprungen (Phase 1 fokussiert auf Aenderungserkennung, nicht Neuanlage-Bewertung).")
            continue

        old_text = previous_raw_texts.get(candidate.filename)
        new_text = current_raw_texts.get(candidate.filename)

        if old_text is None or new_text is None:
            print(f"\n{candidate.filename}: Rohtext-Historie fehlt, wird uebersprungen.")
            continue

        hunks = compute_diff_hunks(old_text, new_text)
        print(f"\n{candidate.filename}: {len(hunks)} Aenderungsblock/-bloecke gefunden.")

        if not hunks:
            continue

        full_path = _full_path_for_filename(current_summary.source_file_mtimes, candidate.filename)
        if full_path is None:
            print("  ABBRUCH: Pfad nicht auffindbar.")
            continue

        other_summaries = _other_document_summaries(current_summary, candidate.filename)

        for i, hunk in enumerate(hunks, start=1):
            print(f"\n  Block {i}/{len(hunks)} (Zeilen {hunk.new_start_line}-{hunk.new_end_line}):")
            _handle_hunk(
                filename=candidate.filename,
                full_path=full_path,
                hunk=hunk,
                current_project_concept=current_summary.concept_text,
                other_document_summaries=other_summaries,
                full_document_text=new_text,
                rejection_examples=rejection_examples,
            )

    print("\nSchritt 5/5: Snapshot aktualisieren...")
    save_snapshot(CURATOR_DATA_ROOT, TARGET_PROJECT_NAME, current_summary)
    print("Fertig.")


if __name__ == "__main__":
    run()
