"""
agents/evaluator_agent/drift_judge_prompt.py

VERSION 3 (2026-08-25, kompletter Architektur-Umbau -- siehe Chat-Verlauf,
Recherche-Zusammenfassung "robuste Patch-Architektur"). Der Judge bewertet
jetzt NICHT mehr die ganze Datei mit Zeilennummern (Version 2 fuehrte zu
Uebergeneralisierung: 10 identische Fehlschluesse auf verschiedene Zeilen
eines Merkposten-Abschnitts). Er bewertet stattdessen NUR NOCH die
tatsaechlich vom Nutzer geaenderten Textstellen (DiffHunks aus
diff_hunks.py) -- eine radikal kleinere, praezisere Aufgabe.

WICHTIGE NEUE REGEL (siehe Chat-Verlauf, Ursache des letzten realen
Fehlers): explizite Klarstellung, dass Abschnitte wie "Merkposten",
"TODO", "Wiedervorlage", "Offene Punkte" bewusst offene Arbeitspunkte
enthalten DUERFEN, auch wenn eine uebergeordnete Phase als abgeschlossen
gilt -- das ist KEIN Widerspruch, sondern normale Dokumentationspraxis.

Der Judge liefert jetzt PRO HUNK maximal EIN Urteil (nicht mehr eine
offene Liste ueber das ganze Dokument) -- das begrenzt die Aufgabe auf
das absolute Minimum und macht Uebergeneralisierung strukturell
schwieriger, weil es schlicht nichts "Nachbarliches" gibt, auf das
generalisiert werden koennte.
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
- Wenn du unsicher bist, setze is_supported=true (im Zweifel NICHT als Widerspruch werten) und severity=LOW.
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
