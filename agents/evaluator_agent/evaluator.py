"""
agents/evaluator_agent/evaluator.py

Kern des Bewertungs-Agenten (Evaluator) fuer Phase 1. Zwei Aufgaben in
einem Modul, bewusst getrennt gehalten als zwei Funktionen:

1. run_drift_judge(): ruft Ollama mit dem drift_judge_prompt auf und
   liefert ein strukturiertes DriftJudgment-Ergebnis (Schicht 3 der
   Kaskade, siehe embedding_filter.py-Docstring fuer die Gesamtuebersicht).
2. score_proposal(): wendet das vollstaendige, gewichtete 4-Kriterien-
   Schema an (Faktentreue 0.4, Vollstaendigkeit 0.25, Konsistenz 0.2,
   Sicherheit 0.15 -- siehe Chat-Verlauf 2026-08-22, Recherche zu LLM-
   Evaluator-Rubrics) -- das ist die FINALE Freigabe-Entscheidung, ob der
   Nutzer den Vorschlag ueberhaupt zu Gesicht bekommt.

WICHTIG -- Architekturprinzip (siehe Chat-Verlauf 2026-08-23): dieser
Evaluator ist bewusst NICHT curator-spezifisch geschrieben. run_drift_judge
ist zwar aktuell auf den Curator-Anwendungsfall zugeschnitten (Vault-
Dokument vs. Projektstand), aber score_proposal() arbeitet auf einer
generischen ScoredCriterion-Struktur, die spaeter auch der Builder-Agent
fuer seine eigenen Vorschlaege nutzen kann -- nur die Bewertungs-PROMPTS
unterscheiden sich pro Agent, nicht die Aggregations-/Schwellenwert-Logik.

Ollama-Aufruf-Vertrag (siehe AI_Project_Reviewer/ollama_client.py als
Vorbild -- NICHT importiert, siehe Kopplungsprinzip aus concept_loader.py,
sondern hier bewusst minimal selbst nachgebaut, weil wir nur EINEN
einfachen JSON-Aufruf brauchen, kein volles Fehlerbehandlungs-Set wie dort):
    POST http://localhost:11434/api/generate
    { "model": ..., "prompt": ..., "format": "json", "options": {"temperature": 0}, "stream": false }
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import requests

from agents.evaluator_agent.drift_judge_prompt import build_drift_judge_prompt

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5-coder:latest"  # gleiches Modell wie in concept_summary.json beobachtet


class EvaluatorError(Exception):
    """Fehler beim Ollama-Aufruf oder beim Parsen der Judge-Antwort."""


@dataclass(frozen=True)
class DriftJudgment:
    filename: str
    reasoning: str
    has_drift: bool
    severity: str
    contradiction_summary: str
    suggested_update: str


def run_drift_judge(
    filename: str,
    document_summary: str,
    current_project_concept: str,
    recent_worklog_summaries: str,
    model: str = DEFAULT_MODEL,
    timeout_seconds: int = 120,
) -> DriftJudgment:
    """Fuehrt EINEN Ollama-Aufruf fuer EIN Dokument aus. Wird von
    run_drift_check.py (Orchestrator) pro durchgelassenem Kandidaten aus
    Schicht 2 aufgerufen -- nicht batchweise, um Fehler pro Dokument klar
    zuordnen zu koennen."""
    prompt = build_drift_judge_prompt(
        filename=filename,
        document_summary=document_summary,
        current_project_concept=current_project_concept,
        recent_worklog_summaries=recent_worklog_summaries,
    )

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "format": "json",
                "options": {"temperature": 0},
                "stream": False,
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise EvaluatorError(
            "Ollama nicht erreichbar unter localhost:11434. Ist ollama serve gestartet?"
        ) from exc
    except requests.exceptions.Timeout as exc:
        raise EvaluatorError(f"Ollama Timeout nach {timeout_seconds}s fuer {filename}.") from exc
    except requests.exceptions.HTTPError as exc:
        raise EvaluatorError(f"Ollama HTTP-Fehler fuer {filename}: {exc}") from exc

    raw_text = response.json().get("response", "")

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise EvaluatorError(
            f"Ollama-Antwort fuer {filename} ist kein valides JSON:\n{raw_text[:500]}"
        ) from exc

    try:
        return DriftJudgment(
            filename=filename,
            reasoning=parsed["reasoning"],
            has_drift=bool(parsed["has_drift"]),
            severity=parsed["severity"],
            contradiction_summary=parsed.get("contradiction_summary", ""),
            suggested_update=parsed.get("suggested_update", ""),
        )
    except KeyError as exc:
        raise EvaluatorError(
            f"Ollama-Antwort fuer {filename} fehlt erwartetes Feld: {exc}.\n"
            f"Rohantwort: {raw_text[:500]}"
        ) from exc


# ---------------------------------------------------------------------------
# Vier-Kriterien-Scoring-Schema (finale Freigabe-Entscheidung, generisch)
# ---------------------------------------------------------------------------

CRITERIA_WEIGHTS = {
    "faktentreue": 0.40,
    "vollstaendigkeit": 0.25,
    "konsistenz": 0.20,
    "sicherheit": 0.15,
}

MIN_WEIGHTED_SCORE = 7.0
MIN_SINGLE_CRITERION_SCORE = 4.0


@dataclass(frozen=True)
class CriterionScore:
    name: str
    score: float  # 1-10
    justification: str


@dataclass(frozen=True)
class ScoredProposal:
    weighted_score: float
    criterion_scores: list[CriterionScore]
    approved: bool
    rejection_reason: str | None


def score_proposal(criterion_scores: list[CriterionScore]) -> ScoredProposal:
    """Wendet das gewichtete Schwellenwert-Schema an (siehe Chat-Verlauf
    2026-08-22): approved nur, wenn gewichteter Gesamtscore >= 7.0 UND
    KEIN Einzelkriterium unter 4.0 liegt.

    Diese Funktion faellt selbst KEIN LLM-Urteil -- sie aggregiert nur
    bereits vorhandene CriterionScore-Objekte. Woher diese Scores kommen
    (Ollama-Aufruf, deterministische Heuristik, oder eine Mischung), ist
    Sache des Aufrufers -- bewusste Trennung von Bewertung und Aggregation.
    """
    provided_names = {c.name for c in criterion_scores}
    expected_names = set(CRITERIA_WEIGHTS.keys())
    if provided_names != expected_names:
        raise EvaluatorError(
            f"score_proposal erwartet genau die Kriterien {expected_names}, "
            f"erhalten: {provided_names}."
        )

    weighted_score = sum(
        c.score * CRITERIA_WEIGHTS[c.name] for c in criterion_scores
    )

    low_scoring = [c for c in criterion_scores if c.score < MIN_SINGLE_CRITERION_SCORE]

    if low_scoring:
        names = ", ".join(c.name for c in low_scoring)
        return ScoredProposal(
            weighted_score=weighted_score,
            criterion_scores=criterion_scores,
            approved=False,
            rejection_reason=f"Einzelkriterium unter Mindestwert {MIN_SINGLE_CRITERION_SCORE}: {names}",
        )

    if weighted_score < MIN_WEIGHTED_SCORE:
        return ScoredProposal(
            weighted_score=weighted_score,
            criterion_scores=criterion_scores,
            approved=False,
            rejection_reason=(
                f"Gewichteter Score {weighted_score:.2f} unter Mindestwert {MIN_WEIGHTED_SCORE}."
            ),
        )

    return ScoredProposal(
        weighted_score=weighted_score,
        criterion_scores=criterion_scores,
        approved=True,
        rejection_reason=None,
    )


def score_drift_judgment_heuristically(judgment: DriftJudgment) -> ScoredProposal:
    """Erste, einfache Ableitung der vier Kriterien-Scores AUS dem
    DriftJudgment selbst -- ohne einen zweiten Ollama-Aufruf. Bewusst als
    Uebergangsloesung markiert (siehe TODO unten): fuer Phase 1 ausreichend,
    weil wir nur EIN Urteil (has_drift/severity) in vier Kriterien
    uebersetzen, nicht vier unabhaengige Urteile einholen.

    TODO (spaetere Verfeinerung, kein Blocker fuer Phase 1): pruefen, ob
    ein zweiter, dedizierter Scoring-Prompt (der explizit alle vier
    Kriterien einzeln bewertet) bessere/robustere Ergebnisse liefert als
    diese Heuristik. Fuer den ersten End-to-End-Test bewusst einfach
    gehalten, siehe Chat-Verlauf 2026-08-23.
    """
    if not judgment.has_drift:
        # Kein Drift erkannt -- Vorschlag ist "nichts zu tun", das ist
        # automatisch maximal vertrauenswuerdig.
        return score_proposal(
            [
                CriterionScore("faktentreue", 10.0, "Kein Widerspruch erkannt."),
                CriterionScore("vollstaendigkeit", 10.0, "Nichts zu aktualisieren."),
                CriterionScore("konsistenz", 10.0, "Keine Aenderung, keine Inkonsistenz moeglich."),
                CriterionScore("sicherheit", 10.0, "Keine Schreiboperation vorgeschlagen."),
            ]
        )

    severity_to_score = {"LOW": 5.0, "MEDIUM": 7.0, "HIGH": 9.0}
    base_score = severity_to_score.get(judgment.severity, 5.0)

    has_concrete_suggestion = bool(judgment.suggested_update.strip())

    return score_proposal(
        [
            CriterionScore(
                "faktentreue",
                base_score,
                f"Judge-Severity: {judgment.severity}. {judgment.contradiction_summary}",
            ),
            CriterionScore(
                "vollstaendigkeit",
                base_score if has_concrete_suggestion else base_score - 3.0,
                "Konkreter Update-Vorschlag vorhanden." if has_concrete_suggestion
                else "Kein konkreter Update-Vorschlag vom Judge geliefert.",
            ),
            CriterionScore(
                "konsistenz", 8.0, "Noch nicht gegen Tagging-/Linking-Konventionen geprueft (spaeterer Baustein)."
            ),
            CriterionScore(
                "sicherheit", 9.0, "Nur ein Vorschlag, keine automatische Schreiboperation (Human-in-the-Loop bleibt)."
            ),
        ]
    )
