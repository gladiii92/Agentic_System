"""
agents/evaluator_agent/evaluator.py

VERSION 4 (2026-08-26, Vollkontext-Ergaenzung -- siehe Chat-Verlauf und
drift_judge_prompt.py-Docstring fuer die volle Begruendung).

Aenderung gegenueber Version 3:
- run_drift_judge() bekommt einen neuen Pflichtparameter
  full_document_text: str -- der volle aktuelle Text derselben Datei,
  aus der der bewertete Hunk stammt. Wird 1:1 an build_drift_judge_prompt()
  durchgereicht.
- Der Ollama-Request setzt jetzt explizit "num_ctx": 8192. Grund (siehe
  Chat-Verlauf-Recherche): Ollama laedt Modelle ohne expliziten num_ctx
  oft mit einem sehr kleinen Default-Kontextfenster (teils nur 2048-4096
  Tokens), unabhaengig vom nativen Modell-Limit (qwen2.5-coder unterstuetzt
  nativ 32K). Ohne diese explizite Angabe wuerde der neu hinzugefuegte
  Volltext-Kontext bei laengeren Dokumenten lautlos abgeschnitten -- exakt
  dasselbe Grundproblem wie beim urspruenglichen Bug, nur eine Ebene
  tiefer. 8192 Tokens sind fuer die aktuelle Zielhardware (RTX 2070 Super,
  8GB VRAM) sicher und reichen fuer Dokumente bis ca. 25.000-30.000
  Zeichen -- fuer laengere Dokumente ist Chunking ein separates, noch
  nicht umgesetztes Folgethema (siehe Chat-Verlauf).

DEFAULT_MODEL bleibt qwen2.5-coder:latest (bewaehrt fuer die
Analyse-Aufgabe, siehe Chat-Verlauf A/B-Test 2026-08-24).
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import requests

from agents.evaluator_agent.drift_judge_prompt import build_drift_judge_prompt

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen2.5-coder:latest"
DEFAULT_NUM_CTX = 8192


class EvaluatorError(Exception):
    """Fehler beim Ollama-Aufruf oder beim Parsen der Judge-Antwort."""


@dataclass(frozen=True)
class HunkJudgment:
    is_meaningful: bool
    is_supported: bool  # True = Text ist durch Projektstand belegt/neutral, KEIN Widerspruch
    severity: str
    reasoning: str
    contradiction_summary: str


def run_drift_judge(
    filename: str,
    hunk_diff_text: str,
    current_project_concept: str,
    recent_worklog_summaries: str,
    full_document_text: str,
    model: str = DEFAULT_MODEL,
    timeout_seconds: int = 90,
    num_ctx: int = DEFAULT_NUM_CTX,
) -> HunkJudgment:
    """Bewertet EINEN Hunk. Wird von run_drift_check.py fuer JEDEN
    DiffHunk einzeln aufgerufen.

    full_document_text: voller aktueller Text derselben Datei, aus der
    der Hunk stammt -- reine Referenz fuer den Judge, damit Widersprueche
    INNERHALB desselben Dokuments (z.B. Statustabelle vs. Fazit-Satz)
    erkennbar werden, auch wenn sie ausserhalb des kleinen
    Hunk-Kontextfensters liegen.
    """
    prompt = build_drift_judge_prompt(
        filename=filename,
        hunk_diff_text=hunk_diff_text,
        current_project_concept=current_project_concept,
        recent_worklog_summaries=recent_worklog_summaries,
        full_document_text=full_document_text,
    )

    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": model,
                "prompt": prompt,
                "format": "json",
                "options": {"temperature": 0, "num_ctx": num_ctx},
                "stream": False,
            },
            timeout=timeout_seconds,
        )
        response.raise_for_status()
    except requests.exceptions.ConnectionError as exc:
        raise EvaluatorError("Ollama nicht erreichbar unter localhost:11434.") from exc
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
        return HunkJudgment(
            is_meaningful=bool(parsed["is_meaningful"]),
            is_supported=bool(parsed["is_supported"]),
            severity=parsed["severity"],
            reasoning=parsed["reasoning"],
            contradiction_summary=parsed.get("contradiction_summary", ""),
        )
    except KeyError as exc:
        raise EvaluatorError(
            f"Ollama-Antwort fuer {filename} fehlt erwartetes Feld: {exc}.\nRohantwort: {raw_text[:500]}"
        ) from exc


# ---------------------------------------------------------------------------
# Vier-Kriterien-Scoring-Schema (unveraendert seit 2026-08-22, bewaehrt)
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
            f"score_proposal erwartet genau die Kriterien {expected_names}, erhalten: {provided_names}."
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


def score_judgment_heuristically(judgment: HunkJudgment) -> ScoredProposal:
    """Wird NUR aufgerufen, wenn judgment.is_supported=False (also ein
    echter Widerspruch behauptet wird) UND judgment.is_meaningful=True --
    triviale/neutrale Hunks werden bereits in run_drift_check.py vorher
    aussortiert, ohne ueberhaupt gescored zu werden."""
    severity_to_score = {"LOW": 5.0, "MEDIUM": 7.0, "HIGH": 9.0}
    base_score = severity_to_score.get(judgment.severity, 5.0)

    return score_proposal(
        [
            CriterionScore("faktentreue", base_score, judgment.contradiction_summary),
            CriterionScore("vollstaendigkeit", base_score, judgment.reasoning),
            CriterionScore("konsistenz", 8.0, "Noch nicht gegen Tagging-/Linking-Konventionen geprueft."),
            CriterionScore("sicherheit", 9.0, "Nur ein Vorschlag, keine automatische Schreiboperation."),
        ]
    )
