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
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
from pathlib import Path

import time

from dotenv import load_dotenv

load_dotenv()

from agents.curator_agent.concept_loader import refresh_and_load
from agents.curator_agent.diff_presenter import build_unified_diff
from agents.evaluator_agent.evaluator import (
    EvaluatorError,
    run_drift_judge,
    run_full_audit_judge,
    score_judgment_heuristically,
)
from agents.evaluator_agent.full_audit_judge_prompt import build_full_audit_judge_prompt
from agents.evaluator_agent.patch_writer import PatchWriterError, write_patch
from agents.evaluator_agent.rejection_history import (
    format_for_prompt,
    load_rejections,
    record_rejection,
)
from patching.document_chunker import compute_document_chunks, render_chunk_for_prompt
from patching.evidence_extractor import extract_evidence
from patching.evidence_models import Evidence
from patching.patch_applier import apply_patch
from patching.patch_validator import validate_patch
from agents.evaluator_agent.cross_chunk_judge import (
    CrossChunkJudgeError,
    run_cross_chunk_judge,
)

AI_PROJECT_REVIEWER_REPO_PATH = Path(r"G:\DAVID\Desktop\GitHub\AI_Project_Reviewer")
REJECTION_HISTORY_ROOT = Path(r"G:\DAVID\Desktop\GitHub\Agentic_System\data\rejection_history")
TARGET_PROJECT_NAME = "AI_Project_Reviewer"
AGENT_NAME = "curator_agent"

MAX_FULL_DOCUMENT_CHARS = 20_000

# Identisch zu run_drift_check.py -- Ollama bewusst ausgeschlossen fuer
# den Patch-Writer (siehe dortige Begruendung, empirisch belegte
# Modell-Faehigkeitsgrenze bei dieser Lokalisierungsaufgabe).
PATCH_WRITER_MODEL_TIERS = ("groq",)

# Wartezeit in Sekunden zwischen Groq-API-Calls, damit das Token-Limit
# (TPM) des Free Tiers nicht durch aufeinanderfolgende Patch-Writer-Calls
# (v.a. Chunk-Funds + darauffolgender Cross-Chunk-Patch) ueberschritten
# wird. Real beobachteter 429-Fehler (2026-09-10): Limit 8000 TPM,
# Used 5084 + Requested 5054 -> Retry-After 16s. 30s geben zusaetzliche
# Reserve, ohne den Lauf unnoetig zu verlangsamen.
GROQ_COOLDOWN_SECONDS = 30


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
            print(f"    FEHLER bei Stufe '{tier}': {exc}")
            continue

        print(f"    [DEBUG] exact_old_text (Stufe '{tier}'): {proposed_patch.exact_old_text!r}")
        print(f"    [DEBUG] replacement_text (Stufe '{tier}'): {proposed_patch.replacement_text!r}")
        print(f"    [DEBUG] change_summary (Stufe '{tier}'): {proposed_patch.change_summary!r}")

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

    print(f"    [DEBUG] chunk_text an Judge ({len(chunk_text)} Zeichen): {chunk_text[:300]!r}{'...' if len(chunk_text) > 300 else ''}")
    print(f"    [DEBUG] full_document_text an Judge: {len(clipped_full_text)} Zeichen (gekuerzt: {len(clipped_full_text) < len(current_full_text_for_judge)})")

    try:
        # Full-Audit verwendet speziellen Prompt für Konsistenzprüfung (kein Hunk-Diff)
        from agents.evaluator_agent.full_audit_judge_prompt import build_full_audit_judge_prompt
        from agents.evaluator_agent.evaluator import run_full_audit_judge
        
        judgment = run_full_audit_judge(
            filename=filename,
            document_section_to_evaluate=chunk_text,
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

    _present_and_apply_patch(
        filename=filename,
        full_path=full_path,
        current_full_text=current_full_text,
        validated_patch=validated_patch,
        successful_tier=successful_tier,
        contradiction_summary=judgment.contradiction_summary,
    )


def _present_and_apply_patch(
    filename: str,
    full_path: Path,
    current_full_text: str,
    validated_patch,
    successful_tier: str,
    contradiction_summary: str,
) -> None:
    """Gemeinsamer Human-in-the-Loop-Ablauf: Patch im Speicher anwenden, als Diff
    zeigen, Nutzer fragen, ggf. schreiben oder ablehnen (mit Rejection-Log)."""
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
            contradiction_summary=contradiction_summary,
            suggested_update=validated_patch.replacement_text,
            proposed_text=validated_patch.replacement_text,
            rejection_reason=reason,
        )
        print("-> Abgelehnt. In Ablehnungs-Historie gespeichert fuer kuenftige Prompts.")

def _status_rank_of(text: str) -> int:
    """Deterministische Status-Hierarchie (offen < nächster Schritt < in arbeit
    < abgeschlossen < abgeschlossen und real verifiziert). 0 = offen/unbekannt."""
    low = text.lower()
    if "abgeschlossen und real verifiziert" in low:
        return 4
    if "abgeschlossen" in low:
        return 3
    if "in arbeit" in low:
        return 2
    if "nächster schritt" in low:
        return 1
    return 0


def _build_cross_chunk_patch_context(evidence_items: list[Evidence]) -> str:
    """Baut fuer den Patch-Writer einen Diff-artigen Kontext aus den
    widersprechenden Evidence-Aussagen: die aeltere (zu korrigierende) Stelle
    gegen die neuere, maessgebliche Referenz.

    Deterministische Vorauswahl (kein LLM nötig):
      - Referenz = Evidence-Aussage mit dem NEUESTEN Datum und Status-Rang >= 3
        ("abgeschlossen...").
      - Zu korrigieren = alle [TABELLE]-Aussagen mit niedrigerem Status-Rang
        als die Referenz.

    Gibt es keine solche Konstellation (z.B. Referenz ist selbst eine offene
    Aussage), liefert die Funktion einen leeren String -- dann entscheidet der
    Patch-Writer allein anhand des Volltextes.
    """
    dated = [ev for ev in evidence_items if ev.date]
    if not dated:
        return ""

    reference = max(dated, key=lambda ev: ev.date)
    if _status_rank_of(reference.text) < 3:
        return ""

    to_fix = [
        ev
        for ev in evidence_items
        if ev.category == "TABELLE" and _status_rank_of(ev.text) < _status_rank_of(reference.text)
    ]
    if not to_fix:
        return ""

    lines = [
        "Anleitung zur Korrekturrichtung (Datums-Rangfolgen-Regel): Die folgenden",
        "aelteren/undatierten Stellen im Dokument widersprechen der NEUEREN, datierten",
        "Referenzaussage unten. Korrigiere die aelteren Stellen so, dass sie zur",
        "Referenz passen -- nicht umgekehrt.",
        "",
        "Zu korrigierende Stelle(n) (aeltere undatierte Aussage, steht aktuell so im Dokument):",
    ]
    for ev in to_fix:
        lines.append(f"+ {ev.compact}")
    lines.append("")
    lines.append("Maessgebliche neuere Referenzaussage (WIRD NICHT geaendert -- an sie wird angeglichen):")
    lines.append(f"- {reference.compact}")
    return "\n".join(lines)


def _handle_cross_chunk_finding(
    filename: str,
    full_path: Path,
    evidence_items: list[Evidence],
    contradiction_summary: str,
    current_project_concept: str,
    rejection_examples: list[str],
) -> None:
    """Cross-Chunk-Widerspruch: erzeugt ueber den Patch-Writer einen Korrektur-
    Vorschlag (mit deterministischer Vorauswahl der zu korrigierenden Stellen),
    validiert ihn und legt ihn dem Nutzer per Human-in-the-Loop vor."""
    current_full_text = full_path.read_text(encoding="utf-8")
    clipped_full_text = _clip_document_text(current_full_text)

    # Cool-down VOR dem Cross-Chunk-Patch-Versuch: der Chunk-Loop hat gerade
    # evtl. einen Patch-Writer-Call (groq) verbraucht; ohne Pause kann der
    # sofort nachfolgende Cross-Chunk-Call das TPM-Limit des Free Tiers
    # sprengen (real beobachtet: 429 "Rate limit reached", Retry 16s).
    print(f"  (Pause {GROQ_COOLDOWN_SECONDS}s vor Cross-Chunk-Patch, um Groq-Rate-Limit (TPM) nicht zu ueberschreiten...)")
    time.sleep(GROQ_COOLDOWN_SECONDS)

    patch_context = _build_cross_chunk_patch_context(evidence_items)
    hunk_text = patch_context or "\n".join(f"- {ev.compact}" for ev in evidence_items)

    validated_patch, successful_tier = _write_patch_with_escalation(
        filename=filename,
        contradiction_summary=contradiction_summary,
        hunk_text=hunk_text,
        current_project_concept=current_project_concept,
        clipped_full_text=clipped_full_text,
        rejection_examples=rejection_examples,
        current_full_text=current_full_text,
    )

    if validated_patch is None:
        print(f"  AUTOMATISCH VERWORFEN: alle Stufen {PATCH_WRITER_MODEL_TIERS} sind an der Patch-Validierung gescheitert.")
        return

    _present_and_apply_patch(
        filename=filename,
        full_path=full_path,
        current_full_text=current_full_text,
        validated_patch=validated_patch,
        successful_tier=successful_tier,
        contradiction_summary=contradiction_summary,
    )

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
    all_evidence: list[Evidence] = []
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
        # Extract evidence from the chunk text (not the rendered prompt)
        raw_chunk_text = chunk.text
        evidence_list = extract_evidence(raw_chunk_text, chunk.chunk_index, chunk.start_line)
        for ev in evidence_list:
            all_evidence.append(ev)
        if chunk.chunk_index < len(chunks) - 1:
            print(f"  (Pause {GROQ_COOLDOWN_SECONDS}s, um Groq-Rate-Limit (TPM) nicht zu ueberschreiten...)")
            time.sleep(GROQ_COOLDOWN_SECONDS)

    # Cross-Chunk Audit: after all chunks processed, check for global contradictions
    if all_evidence:
        print("\n" + "=" * 70)
        print("CROSS-CHUNK AUDIT")
        print("=" * 70)
        evidence_compacts = [ev.compact for ev in all_evidence]
        print(f"  {len(evidence_compacts)} Evidence-Aussagen extrahiert:")
        for ev in evidence_compacts:
            print(f"    - {ev}")
        print()
        try:
            cross_judgment = run_cross_chunk_judge(evidence_compacts)
            print(f"  Cross-Chunk Judge: is_meaningful={cross_judgment.is_meaningful}, is_supported={cross_judgment.is_supported}, severity={cross_judgment.severity}")
            print(f"  Begründung: {cross_judgment.reasoning}")
            if not cross_judgment.is_supported:
                print(f"  Widerspruch: {cross_judgment.contradiction_summary}")
                _handle_cross_chunk_finding(
                    filename=target_filename,
                    full_path=full_path,
                    evidence_items=all_evidence,
                    contradiction_summary=cross_judgment.contradiction_summary,
                    current_project_concept=current_summary.concept_text,
                    rejection_examples=rejection_examples,
                )
        except CrossChunkJudgeError as exc:
            print(f"  FEHLER beim Cross-Chunk Judge: {exc}")
    else:
        print("\n  Keine Evidence-Aussagen extrahiert. Cross-Chunk Audit uebersprungen.")

    print("\nFull-Audit abgeschlossen.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Verwendung: python -m agents.curator_agent.run_full_audit <dateiname>")
        sys.exit(1)
    run(sys.argv[1])
