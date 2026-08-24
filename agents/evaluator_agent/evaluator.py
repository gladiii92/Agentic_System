"""
agents/evaluator_agent/evaluator.py

VERSION 2 (2026-08-24, zeilengenauer Umbau -- siehe Chat-Verlauf). Statt
eines einzelnen DriftJudgment liefert run_drift_judge() jetzt eine LISTE
von DriftFinding-Objekten, jeweils mit exakter line_number. Das
Scoring-Schema (score_proposal, CRITERIA_WEIGHTS) bleibt unveraendert
(bewaehrt, kein Grund zur Aenderung), wird aber jetzt PRO EINZELFINDING
angewendet statt pro Dokument.

DEFAULT_MODEL: zurueckgewechselt auf qwen2.5-coder:latest (siehe
Chat-Verlauf 2026-08-24 -- realer A/B-Test zeigte, dass die Coder-Variante
bei dieser strukturierten Analyse-Aufgabe zuverlaessiger Drift erkennt
als die reine Text-Variante qwen2.5:latest. Fuer den SCHREIB-Vorgang
(proposal_writer.py) bleibt weiterhin qwen2.5:latest -- unterschiedliche
Aufgaben, unterschiedliche beobachtete Staerken, siehe jeweilige Docstrings).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import requests

from agents.evaluator_agent.drift_judge_prompt import build_drift_judge_prompt, number_lines

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5-coder:latest"


class EvaluatorError(Exception):
    """Fehler beim Ollama-Aufruf oder beim Parsen der Judge-Antwort."""


@dataclass(frozen=True)
class DriftFinding:
    filename: str
    line_number: int
    reasoning: str
    severity: str
    contradiction_summary: str
    suggested_update: str


def run_drift_judge(
    filename: str,
    full_document_text: str,
    current_project_concept: str,
    recent_worklog_summaries: str,
    model: str = DEFAULT_MODEL,
    timeout_seconds: int = 180,
) -> list[DriftFinding]:
    """Fuehrt EINEN Ollama-Aufruf fuer EIN Dokument aus, liefert aber
    potenziell MEHRERE Findings zurueck (eines pro erkannter Diskrepanz-
    Zeile). full_document_text ist jetzt der VOLLE Rohtext der Datei
    (nicht mehr nur die Ollama-Zusammenfassung, siehe drift_judge_prompt.py
    Version 2 -- der Judge braucht den echten Text fuer echte
    Zeilennummern)."""
    numbered_text = number_lines(full_document_text)

    prompt = build_drift_judge_prompt(
        filename=filename,
        numbered_document_text=numbered_text,
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

    findings = []
    try:
        for item in parsed.get("findings", []):
            findings.append(
                DriftFinding(
                    filename=filename,
                    line_number=int(item["line_number"]),
                    reasoning=item["reasoning"],
                    severity=item["severity"],
                    contradiction_summary=item["contradiction_summary"],
                    suggested_update=item["suggested_update"],
                )
            )
    except (KeyError, ValueError, TypeError) as exc:
        raise EvaluatorError(
            f"Ollama-Antwort fuer {filename} hat unerwartetes Finding-Format: {exc}.\n"
            f"Rohantwort: {raw_text[:500]}"
        ) from exc

    return findings


# ---------------------------------------------------------------------------
# Vier-Kriterien-Scoring-Schema (unveraendert, wird jetzt PRO FINDING genutzt)
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
    score: float
    justification: str


@dataclass(frozen=True)
class ScoredProposal:
    weighted_score: float
    criterion_scores: list[CriterionScore]
    approved: bool
    rejection_reason: str | None


def score_proposal(criterion_scores: list[CriterionScore]) -> ScoredProposal:
    provided_names = {c.name for c in criterion_scores}
    expected_names = set(CRITERIA_WEIGHTS.keys())
    if provided_names != expected_names:
        raise EvaluatorError(
            f"score_proposal erwartet genau die Kriterien {expected_names}, "
            f"erhalten: {provided_names}."
        )

    weighted_score = sum(c.score * CRITERIA_WEIGHTS[c.name] for c in criterion_scores)

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
            rejection_reason=f"Gewichteter Score {weighted_score:.2f} unter Mindestwert {MIN_WEIGHTED_SCORE}.",
        )

    return ScoredProposal(
        weighted_score=weighted_score, criterion_scores=criterion_scores, approved=True, rejection_reason=None
    )


def score_finding_heuristically(finding: DriftFinding) -> ScoredProposal:
    """Analog zur bisherigen score_drift_judgment_heuristically, jetzt auf
    ein einzelnes DriftFinding angewendet (es gibt kein has_drift=False-
    Findings mehr -- ein Finding EXISTIERT nur, wenn der Judge tatsaechlich
    einen Widerspruch fand; die leere findings-Liste im "kein Drift"-Fall
    wird bereits vom Aufrufer in run_drift_check.py behandelt)."""
    severity_to_score = {"LOW": 5.0, "MEDIUM": 7.0, "HIGH": 9.0}
    base_score = severity_to_score.get(finding.severity, 5.0)

    has_concrete_suggestion = bool(finding.suggested_update.strip())

    return score_proposal(
        [
            CriterionScore(
                "faktentreue", base_score, f"Judge-Severity: {finding.severity}. {finding.contradiction_summary}"
            ),
            CriterionScore(
                "vollstaendigkeit",
                base_score if has_concrete_suggestion else base_score - 3.0,
                "Konkreter Update-Vorschlag vorhanden." if has_concrete_suggestion
                else "Kein konkreter Update-Vorschlag vom Judge geliefert.",
            ),
            CriterionScore("konsistenz", 8.0, "Noch nicht gegen Tagging-/Linking-Konventionen geprueft."),
            CriterionScore("sicherheit", 9.0, "Nur ein Vorschlag, keine automatische Schreiboperation."),
        ]
    )
