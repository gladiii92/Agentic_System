"""
agents/curator_agent/run_full_audit.py

NEUES Modul (2026-08-26, Full-Audit-Feature -- siehe Chat-Verlauf).

Separates, manuell auszufuehrendes Kommando (NICHT Teil des normalen
run_drift_check.py-Ablaufs). Zweck: findet Widersprueche, die BEREITS
im Dokument bestehen, unabhaengig davon, ob sich seit dem letzten
Snapshot etwas geaendert hat -- im Unterschied zu run_drift_check.py,
das NUR auf neu erkannte Aenderungen reagiert (siehe Handover Abschnitt
3 fuer die Begruendung dieser bewussten Trennung).

Beispiel-Anwendungsfall (realer Testfall, siehe Chat-Verlauf): ein Satz
wie "Alle Phasen sind abgeschlossen UND das Projekt ist FERTIG!" der
laengst im Dokument steht und einer Statustabelle im selben Dokument
widerspricht, wird von run_drift_check.py NICHT gefunden, wenn diese
Zeile sich seit dem letzten Snapshot nicht mehr veraendert hat.
run_full_audit.py deckt genau diesen Fall ab, indem es das GESAMTE
Dokument in Chunks durchgeht (patching/document_chunker.py) und JEDEN
Chunk einzeln vom Judge pruefen laesst -- mit dem kompletten
Dokumenttext als Referenz, damit auch Widersprueche ueber Chunk-Grenzen
hinweg erkannt werden (siehe document_chunker.py-Docstring).

Ablauf pro Chunk (WIEDERVERWENDUNG des exakt gleichen, bereits real
verifizierten Mechanismus wie run_drift_check.py -- KEINE neue
Judge-/Patch-Writer-/Validierungslogik):
1. run_drift_judge() bewertet den Chunk (als "hunk_diff_text" getarnt --
   der Judge behandelt ihn identisch zu einem echten Hunk, siehe
   drift_judge_prompt.py, das keine Annahme ueber Diff-Praefixe macht,
   die fuer die Bewertung zwingend waeren).
2. Bei is_meaningful=True UND is_supported=False: Scoring, dann
   Patch-Writer-Eskalation (gemini -> groq, siehe run_drift_check.py
   PATCH_WRITER_MODEL_TIERS -- Ollama bleibt fuer den Patch-Writer
   bewusst ausgeschlossen, siehe dortige Begruendung).
3. Patch-Validierung + Human-in-the-Loop, IDENTISCH zu run_drift_check.py.

Aufruf: python -m agents.curator_agent.run_full_audit <dateiname>
Beispiel: python -m agents.curator_agent.run_full_audit ROADMAP.md

WICHTIG: dieser Modus verursacht MEHRERE API-Calls PRO Chunk (Judge +
ggf. Patch-Writer-Eskalation) -- bei einem Dokument mit z.B. 800 Zeilen
und 200 Zeilen pro Chunk sind das 4 Chunks, also mindestens 4 Judge-Calls.
Deshalb bewusst NICHT automatisch bei jedem normalen Drift-Check-Lauf,
sondern nur auf explizite Anforderung.
"""

from __future__ import annotations

import sys
from pathlib import Path

import time

from dotenv import load_dotenv

load_dotenv()

from agents.curator_agent.concept_loader import refresh_and_load
from agents.curator_agent.diff_presenter import build_unified_diff
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
from patching.document_chunker import compute_document_chunks, render_chunk_for_prompt
from patching.patch_applier import apply_patch
from patching.patch_validator import validate_patch

AI_PROJECT_REVIEWER_REPO_PATH = Path(r"G:\DAVID\Desktop\GitHub\AI_Project_Reviewer")
REJECTION_HISTORY_ROOT = Path(r"G:\DAVID\Desktop\GitHub\Agentic_System\data\rejection_history")
TARGET_PROJECT_NAME = "AI_Project_Reviewer"
AGENT_NAME = "curator_agent"

MAX_FULL_DOCUMENT_CHARS = 20_000

# Identisch zu run_drift_check.py -- Ollama bewusst ausgeschlossen fuer
# den Patch-Writer (siehe dortige Begruendung, empirisch belegte
# Modell-Faehigkeitsgrenze bei dieser Lokalisierungsaufgabe).
PATCH_WRITER_MODEL_TIERS = ("groq",)


def _clip_document_text(text: str, max_chars: int = MAX_FULL_DOCUMENT_CHARS) -> str:
    if len(text) <= max_chars:
        return text
    return (
        text[:max_chars]
        + f"\n\n[... Dokument gekuerzt, {len(text) - max_chars} weitere Zeichen nicht angezeigt ...]"
    )


def _other_document_summaries(current_summary, exclude_filename: str) -> str:
    parts = []
    for doc in current_summary.document_summaries:
        if doc.path == exclude_filename:
            continue
        parts.append(f"- {doc.path}: {doc.summary}")
    return "\n".join(parts)


def _write_patch_with_escalation(
    filename: str,
    contradiction_summary: str,
    hunk_text: str,
    current_project_concept: str,
    clipped_full_text: str,
    rejection_examples: list[str],
    current_full_text: str,
):
    for tier in PATCH_WRITER_MODEL_TIERS:
        print(f"    Patch-Writer-Versuch (Stufe: {tier})...")
        try:
            proposed_patch = write_patch(
                filename=filename,
                contradiction_summary=contradiction_summary,
                hunk_diff_text=hunk_text,
                current_project_concept=current_project_concept,
                full_document_text=clipped_full_text,
                rejection_examples=rejection_examples,
                model_tier=tier,
            )
        except PatchWriterError as exc:
            print(f"      FEHLER bei Stufe '{tier}': {exc}")
            continue

        validation = validate_patch(proposed_patch, current_full_text)
        if validation.passed:
            print(f"      -> Stufe '{tier}' hat einen validen Patch geliefert.")
            return validation.validated_patch, tier

        print(f"      Stufe '{tier}': Patch-Validierung fehlgeschlagen:")
        for failure in validation.failures:
            print(f"        - {failure}")

    return None, None


def _handle_chunk_finding(
    filename: str,
    full_path: Path,
    chunk_text: str,
    current_project_concept: str,
    other_document_summaries: str,
    rejection_examples: list[str],
) -> None:
    current_full_text_for_judge = full_path.read_text(encoding="utf-8")
    clipped_full_text = _clip_document_text(current_full_text_for_judge)

    try:
        judgment = run_drift_judge(
            filename=filename,
            hunk_diff_text=chunk_text,
            current_project_concept=current_project_concept,
            recent_worklog_summaries=other_document_summaries,
            full_document_text=clipped_full_text,
        )
    except EvaluatorError as exc:
        print(f"    FEHLER beim Judge-Aufruf fuer diesen Chunk: {exc}")
        return

    print(f"    is_meaningful={judgment.is_meaningful}, is_supported={judgment.is_supported}, severity={judgment.severity}")
    print(f"    Begruendung: {judgment.reasoning}")

    if not judgment.is_meaningful or judgment.is_supported:
        print("    -> Kein Widerspruch in diesem Chunk erkannt.")
        return

    scored = score_judgment_heuristically(judgment)
    print(f"    Score: {scored.weighted_score:.2f}, approved={scored.approved}")

    if not scored.approved:
        print(f"    Verworfen vom Evaluator: {scored.rejection_reason}")
        return

    current_full_text = current_full_text_for_judge

    validated_patch, successful_tier = _write_patch_with_escalation(
        filename=filename,
        contradiction_summary=judgment.contradiction_summary,
        hunk_text=chunk_text,
        current_project_concept=current_project_concept,
        clipped_full_text=clipped_full_text,
        rejection_examples=rejection_examples,
        current_full_text=current_full_text,
    )

    if validated_patch is None:
        print(f"    AUTOMATISCH VERWORFEN: alle Stufen {PATCH_WRITER_MODEL_TIERS} sind an der Patch-Validierung gescheitert.")
        return

    result = apply_patch(current_full_text, validated_patch)
    if not result.success:
        print(f"    FEHLER bei der Patch-Anwendung: {result.error_message}")
        return

    print("\n" + "=" * 70)
    print(f"VORSCHAU FUER: {filename} (erzeugt von Stufe: {successful_tier})")
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


def run(target_filename: str) -> None:
    print(f"Starte Full-Audit fuer Datei: {target_filename} (Projekt: {TARGET_PROJECT_NAME})")
    print("Schritt 1/3: Frischer concept_summary-Lauf (kann ca. 1 Minute dauern)...")

    current_summary = refresh_and_load(
        ai_project_reviewer_repo_path=AI_PROJECT_REVIEWER_REPO_PATH,
        target_project_path=AI_PROJECT_REVIEWER_REPO_PATH,
        project_name=TARGET_PROJECT_NAME,
    )
    print(f"  -> {len(current_summary.document_summaries)} Dokument(e) zusammengefasst.")

    full_path = None
    for candidate_path in current_summary.source_file_mtimes:
        if Path(candidate_path).name == target_filename:
            full_path = Path(candidate_path)
            break

    if full_path is None:
        print(f"ABBRUCH: Datei '{target_filename}' nicht im aktuellen Projekt-Scan gefunden.")
        return

    full_text = full_path.read_text(encoding="utf-8")
    other_summaries = _other_document_summaries(current_summary, target_filename)

    print("Schritt 2/3: Dokument in Chunks aufteilen...")
    chunks = compute_document_chunks(full_text)
    print(f"  -> {len(chunks)} Chunk(s) gefunden.")

    rejections = load_rejections(REJECTION_HISTORY_ROOT, AGENT_NAME)
    rejection_examples = format_for_prompt(rejections)

    print("Schritt 3/3: Jeden Chunk einzeln pruefen...")
    for chunk in chunks:
        print(f"\n  Chunk {chunk.chunk_index + 1}/{len(chunks)} (Zeilen {chunk.start_line}-{chunk.end_line}):")
        chunk_text = render_chunk_for_prompt(chunk)
        _handle_chunk_finding(
            filename=target_filename,
            full_path=full_path,
            chunk_text=chunk_text,
            current_project_concept=current_summary.concept_text,
            other_document_summaries=other_summaries,
            rejection_examples=rejection_examples,
        )
        if chunk.chunk_index < len(chunks) - 1:
            print("  (Pause 15s, um Groq-Rate-Limit (TPM) nicht zu ueberschreiten...)")
            time.sleep(15)

    print("\nFull-Audit abgeschlossen.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Verwendung: python -m agents.curator_agent.run_full_audit <dateiname>")
        sys.exit(1)
    run(sys.argv[1])
