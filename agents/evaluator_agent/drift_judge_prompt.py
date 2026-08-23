"""
agents/evaluator_agent/drift_judge_prompt.py

Schicht 3 der Evaluator-Kaskade -- der eigentliche LLM-as-Judge-Prompt fuer
die Frage "widerspricht dieses Vault-Dokument dem aktuellen, echten
Projektstand inhaltlich?". Baustein des Bewertungs-Agenten (Evaluator),
der laut Grundsatzentscheidung (Handover-Dokument, Abschnitt 2.2/2.4)
eine QUERSCHNITTS-Komponente ist -- wird hier zuerst fuer den Curator
gebraucht, spaeter aber auch vom Builder-Agenten genutzt (andere
Kriterien-Instanzen, gleiche Architektur, siehe evaluator.py).

Prompt-Stil bewusst analog zu AI_Project_Reviewer/prompts/reviewer_prompt.py
(vier austauschbare Komponenten: role, task, constraints, output_format),
NICHT Jinja2 -- kein Grund fuer eine Templating-Engine bei so wenigen,
einfachen Platzhaltern (siehe Begruendung im Original-Modul).

Best-Practice-Entscheidungen aus Recherche (siehe Chat-Verlauf 2026-08-22):
- Judge muss ERST begruenden, DANN strikt strukturiert antworten (schlechtes
  Ergebnis bei Freitext-Score ohne Begruendung, siehe G-Eval-Recherche).
- Temperature=0 beim Ollama-Aufruf (Determinismus, siehe ollama_client.py
  aus AI_Project_Reviewer -- call_ollama unterstuetzt das vermutlich schon,
  ggf. beim naechsten Baustein pruefen).
- Bewertung ausschliesslich auf Basis des gegebenen Kontexts, keine
  Spekulation ueber nicht enthaltene Informationen (identische Regel wie
  im Original-reviewer_prompt.py CONSTRAINTS-Block).
"""

from __future__ import annotations

from dataclasses import dataclass

ROLE = """Du bist ein erfahrener Technical Writer und Projektmanager. Du prüfst, ob ein einzelnes Dokument aus einer internen Projekt-Wissensdatenbank (Obsidian-Vault) noch inhaltlich zum tatsächlichen, aktuellen Stand eines Software-Projekts passt."""

TASK_TEMPLATE = """Vergleiche die folgende Vault-Dokument-Zusammenfassung mit dem tatsächlichen, aktuellen Gesamtprojektstand.

Dateiname: {filename}

Zusammenfassung des Vault-Dokuments (das, was aktuell im Vault steht):
{document_summary}

Tatsächlicher, aktueller Gesamtprojektstand (aus frischem Code-/Vault-Scan):
{current_project_concept}

Zusätzlicher Kontext -- neuere Arbeitsprotokolle (Worklogs), die zeitlich NACH diesem Dokument entstanden sind und den tatsächlichen Fortschritt zeigen:
{recent_worklog_summaries}

Prüfe:
- Behauptet das Vault-Dokument einen Projektstatus (z.B. eine Phase, einen Fertigstellungsgrad, eine geplante vs. bereits umgesetzte Funktion), der dem tatsächlichen Stand laut den Worklogs/dem Gesamtprojektstand widerspricht?
- Ist die Diskrepanz relevant (z.B. veraltete Phase-Angabe, längst umgesetzte Funktion wird noch als "geplant" beschrieben) oder nur unwesentlich (z.B. leicht andere Wortwahl, gleiche Kernaussage)?"""

CONSTRAINTS = """Wichtige Einschränkungen:
- Bewerte NUR auf Basis der oben gegebenen Texte. Spekuliere NICHT über Informationen, die dort nicht enthalten sind.
- Eine andere Formulierung derselben Aussage ist KEIN Widerspruch.
- Nur ein tatsächlicher inhaltlicher Widerspruch zum beschriebenen Projektstand zählt als Drift.
- Wenn du unsicher bist, ob ein Widerspruch besteht, stufe severity als LOW ein statt zu raten.
- Antworte ausschließlich mit validem JSON, kein Freitext davor oder danach."""

OUTPUT_FORMAT = """Antworte ausschließlich mit einem JSON-Objekt exakt in dieser Struktur:

{
  "reasoning": "kurze Begründung deiner Einschätzung, 2-4 Sätze, BEVOR du zum Urteil kommst",
  "has_drift": true oder false,
  "severity": "LOW" | "MEDIUM" | "HIGH",
  "contradiction_summary": "falls has_drift=true: was genau widerspricht sich, 1-2 Sätze. Sonst leerer String.",
  "suggested_update": "falls has_drift=true: konkreter Vorschlag, wie das Vault-Dokument angepasst werden sollte. Sonst leerer String."
}"""


@dataclass(frozen=True)
class DriftJudgePromptComponents:
    role: str = ROLE
    task_template: str = TASK_TEMPLATE
    constraints: str = CONSTRAINTS
    output_format: str = OUTPUT_FORMAT


def build_drift_judge_prompt(
    filename: str,
    document_summary: str,
    current_project_concept: str,
    recent_worklog_summaries: str,
    components: DriftJudgePromptComponents | None = None,
) -> str:
    """Setzt die vier Prompt-Bausteine zu einem finalen String zusammen.

    Args:
        filename: Name des zu pruefenden Vault-Dokuments (z.B. "ROADMAP.md").
        document_summary: Aktuelle Ollama-Zusammenfassung dieses Dokuments.
        current_project_concept: concept_text aus dem aktuellen ConceptSummary
            (Gesamtprojektstand laut frischem Scan).
        recent_worklog_summaries: Zusammengefuegter Text aus den summary-
            Feldern aller Worklog-Dokumente, die neuer sind als das zu
            pruefende Dokument (Herleitung "neuer als" folgt in
            evaluator.py, nicht in diesem Modul).
    """
    components = components or DriftJudgePromptComponents()
    task = components.task_template.format(
        filename=filename,
        document_summary=document_summary,
        current_project_concept=current_project_concept,
        recent_worklog_summaries=recent_worklog_summaries or "(keine neueren Worklogs vorhanden)",
    )
    return "\n\n".join([components.role, task, components.constraints, components.output_format])
