"""
agents/evaluator_agent/drift_judge_prompt.py

VERSION 4 (2026-08-25, Severity-Kalibrierung -- siehe Chat-Verlauf: Judge
stufte einen klar durch Worklogs belegten Widerspruch nur als LOW ein,
was zu einem Score unter der Mindestschwelle fuehrte, obwohl die
inhaltliche Analyse selbst korrekt und bestimmt war). Aenderung
gegenueber Version 3: CONSTRAINTS enthaelt jetzt eine explizite
Severity-Definition mit Ankerbeispielen, damit der Judge nicht mehr
durchgehend zu LOW tendiert.
"""

from __future__ import annotations

from dataclasses import dataclass

ROLE = """Du bist ein erfahrener Technical Writer und Projektmanager. Du bewertest EINE EINZELNE, bereits identifizierte Textänderung in einem Vault-Dokument -- du suchst NICHT selbst nach Änderungen, die Stelle ist bereits bekannt."""

TASK_TEMPLATE = """Folgende Textänderung wurde in einem Vault-Dokument vorgenommen (- = alter Text, + = neuer Text, ohne Präfix = unveränderter Kontext):

Dateiname: {filename}

Änderung:
{hunk_diff_text}

Tatsächlicher, aktueller Gesamtprojektstand (aus frischem Code-/Vault-Scan):
{current_project_concept}

Zusätzlicher Kontext -- neuere Arbeitsprotokolle (Worklogs):
{recent_worklog_summaries}

Beurteile NUR diese eine Änderung: Ist der NEUE Text (+) durch den tatsächlichen Projektstand belegt, widerlegt, oder neutral (weder belegt noch widerlegt)?"""

CONSTRAINTS = """Wichtige Einschränkungen:
- Bewerte NUR die gezeigte Änderung. Spekuliere NICHT über andere Teile des Dokuments, die du hier nicht siehst.
- WICHTIG: Wenn der Kontext auf einen Abschnitt wie "Merkposten", "TODO", "Wiedervorlage", "Offene Punkte", "Nächste Schritte" hindeutet, ist es NORMAL und KEIN Widerspruch, dass dort offene Aufgaben stehen -- auch wenn andernorts im Projekt eine übergeordnete Phase als abgeschlossen gilt. Melde das NICHT als is_supported=false.
- "is_supported=false" bedeutet: der NEUE Text behauptet etwas, das der Projektstand/die Worklogs AKTIV UND KONKRET widerlegen (z.B. eine Phase als "Offen" bezeichnen, die laut Worklogs nachweislich fertig ist).
- "is_meaningful=false" bedeutet: die Änderung ist trivial (Tippfehler, Formatierung, Synonym) und braucht keine weitere Aktion.

SEVERITY-EINSTUFUNG (bitte genau befolgen, nicht durchgehend LOW wählen):
- HIGH: Die Änderung behauptet einen GESAMTPROJEKTSTATUS (z.B. "alles fertig", "Projekt abgeschlossen"), der durch die Worklogs EINDEUTIG UND UMFASSEND widerlegt wird (mehrere offene Phasen laut Worklogs).
- MEDIUM: Die Änderung behauptet den Status EINER EINZELNEN, KONKRET BENANNTEN Phase/Funktion, der durch die Worklogs eindeutig widerlegt wird.
- LOW: Die Änderung ist zwar nicht ganz präzise, aber nur in einer Nuance falsch, oder die Worklogs liefern nur einen indirekten/schwachen Beleg.
- Ein Widerspruch, den du selbst in deiner Begründung als "eindeutig durch die Worklogs belegt" beschreibst, ist NIEMALS LOW -- mindestens MEDIUM.
- Wenn du unsicher bist, OB überhaupt ein Widerspruch besteht, setze is_supported=true. Wenn du dir SICHER bist, DASS ein Widerspruch besteht, aber unsicher über das genaue Ausmaß, wähle MEDIUM als Standardfall, nicht LOW.
- Antworte ausschließlich mit validem JSON, kein Freitext davor oder danach."""

OUTPUT_FORMAT = """Antworte ausschließlich mit einem JSON-Objekt exakt in dieser Struktur:

{
  "is_meaningful": true,
  "is_supported": false,
  "severity": "LOW",
  "reasoning": "kurze Begründung, 2-3 Sätze",
  "contradiction_summary": "falls is_supported=false: was genau widerspricht sich. Sonst leerer String."
}"""


@dataclass(frozen=True)
class DriftJudgePromptComponents:
    role: str = ROLE
    task_template: str = TASK_TEMPLATE
    constraints: str = CONSTRAINTS
    output_format: str = OUTPUT_FORMAT


def build_drift_judge_prompt(
    filename: str,
    hunk_diff_text: str,
    current_project_concept: str,
    recent_worklog_summaries: str,
    components: DriftJudgePromptComponents | None = None,
) -> str:
    components = components or DriftJudgePromptComponents()
    task = components.task_template.format(
        filename=filename,
        hunk_diff_text=hunk_diff_text,
        current_project_concept=current_project_concept,
        recent_worklog_summaries=recent_worklog_summaries or "(keine neueren Worklogs vorhanden)",
    )
    return "\n\n".join([components.role, task, components.constraints, components.output_format])
