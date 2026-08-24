"""
agents/evaluator_agent/proposal_writer_prompt.py

Vierter Prompt-Baustein. VERSION 2 (2026-08-24, nach realem Testfehler --
siehe Chat-Verlauf): erzeugt jetzt NUR den korrigierten Text fuer EINEN
Markdown-Abschnitt, nicht mehr die ganze Datei. Der betroffene Abschnitt
wird von section_locator.py bestimmt; der Rest der Datei wird
PROGRAMMATISCH unveraendert wieder zusammengefuegt (siehe run_drift_check.py).

WARUM DIESE AENDERUNG: der urspruengliche "ganze Datei neu ausgeben"-Ansatz
fuehrte in einem echten Testlauf zu drei Fehlern gleichzeitig: (1)
mehrere unbeteiligte Abschnitte wurden durch identischen Platzhaltertext
ersetzt, (2) bereits abgeschlossene Phasen wurden faelschlich auf "Offen"
zurueckgesetzt, (3) der eigene Eingabeprompt wurde ins Ergebnis geleakt.
Kleinerer Aufgabenumfang (ein Abschnitt statt der ganzen Datei) reduziert
das Risiko aller drei Fehlerarten strukturell.

Few-Shot-Lernen aus Ablehnungen (siehe rejection_history.py) bleibt
unveraendert bestehen.
"""

from __future__ import annotations

from dataclasses import dataclass

ROLE = """Du bist ein erfahrener Technical Writer. Du aktualisierst EINEN einzelnen Abschnitt eines Markdown-Dokuments aus einer internen Projekt-Wissensdatenbank, basierend auf einer bereits getroffenen fachlichen Einschätzung."""

TASK_TEMPLATE = """Ein Reviewer hat folgende Diskrepanz festgestellt, die genau diesen EINEN Abschnitt betrifft:

Dateiname: {filename}
Abschnitts-Überschrift: {section_heading}
Widerspruch: {contradiction_summary}
Beschreibender Verbesserungsvorschlag des Reviewers: {suggested_update}

Aktueller Text NUR dieses einen Abschnitts (inklusive Überschrift):
---BEGINN ABSCHNITT---
{section_text}
---ENDE ABSCHNITT---

Tatsächlicher, aktueller Gesamtprojektstand (zur Orientierung, NICHT Teil des zu erzeugenden Texts):
{current_project_concept}

Erzeuge den korrigierten Text NUR für diesen einen Abschnitt (inklusive der Überschrift-Zeile am Anfang)."""

CONSTRAINTS_TEMPLATE = """Wichtige Einschränkungen:
- Gib AUSSCHLIESSLICH den Text für DIESEN EINEN Abschnitt zurück, beginnend mit der Überschrift-Zeile.
- Gib NICHT die ganze Datei, NICHT andere Abschnitte, NICHT den obigen Projektstand-Text zurück.
- Erfinde KEINE Fakten, die nicht im "tatsächlichen Projektstand" oben belegt sind.
- Behalte Formatierung und Stil des Originals bei (Tabellen, Aufzählungen, Markdown-Syntax).
- Ändere nur, was durch den Widerspruch begründet ist.
- Falls eine Phase laut Original bereits "Abgeschlossen" war, darf der Status NIE rückwärts auf "Offen" gesetzt werden -- nur der ECHTE, im Projektstand belegte Status darf eingetragen werden.
{rejection_examples_block}"""

OUTPUT_FORMAT = """Antworte ausschließlich mit einem JSON-Objekt exakt in dieser Struktur:

{
  "updated_section_text": "der korrigierte Text NUR dieses Abschnitts, mit \\n für Zeilenumbrüche",
  "change_summary": "1-2 Sätze, was konkret geändert wurde"
}"""


@dataclass(frozen=True)
class ProposalWriterPromptComponents:
    role: str = ROLE
    task_template: str = TASK_TEMPLATE
    constraints_template: str = CONSTRAINTS_TEMPLATE
    output_format: str = OUTPUT_FORMAT


def build_proposal_writer_prompt(
    filename: str,
    section_heading: str,
    section_text: str,
    contradiction_summary: str,
    suggested_update: str,
    current_project_concept: str,
    rejection_examples: list[str] | None = None,
    components: ProposalWriterPromptComponents | None = None,
) -> str:
    components = components or ProposalWriterPromptComponents()

    task = components.task_template.format(
        filename=filename,
        section_heading=section_heading or "(kein Überschrift-Text, Anfang der Datei)",
        section_text=section_text,
        contradiction_summary=contradiction_summary,
        suggested_update=suggested_update,
        current_project_concept=current_project_concept,
    )

    if rejection_examples:
        examples_text = "\n\n".join(rejection_examples)
        rejection_block = (
            f"\n\nWICHTIG -- folgende Vorschlagsarten wurden vom Nutzer in der "
            f"Vergangenheit bereits ABGELEHNT, vermeide aehnliche Fehler:\n{examples_text}"
        )
    else:
        rejection_block = ""

    constraints = components.constraints_template.format(rejection_examples_block=rejection_block)

    return "\n\n".join([components.role, task, constraints, components.output_format])
