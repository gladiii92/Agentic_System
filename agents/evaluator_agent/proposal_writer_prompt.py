"""
agents/evaluator_agent/proposal_writer_prompt.py

VERSION 4 (2026-08-24, zeilengenauer Umbau -- siehe Chat-Verlauf). Erhaelt
jetzt nur noch einen KLEINEN Zeilen-Kontext-Ausschnitt (Standard 5 Zeilen
davor/danach um die vom Judge exakt gemeldete Zeile), statt eines ganzen
Abschnitts. Das minimiert die Aufgabe fuer das Modell auf das absolute
Minimum -- je kleiner der bearbeitete Textbereich, desto geringer das
Risiko von Uebergeneralisierung oder Formatierungs-Beschaedigung (siehe
die beiden vorherigen realen Fehlerfaelle im Chat-Verlauf).
"""

from __future__ import annotations

from dataclasses import dataclass

ROLE = """Du bist ein erfahrener, sehr präziser Technical Writer. Du aktualisierst einen KLEINEN Zeilen-Ausschnitt eines Markdown-Dokuments MINIMAL-INVASIV, basierend auf einer bereits getroffenen fachlichen Einschätzung zu GENAU EINER Zeile. Du änderst NUR das, was konkret belegt ist -- niemals mehr."""

TASK_TEMPLATE = """Ein Reviewer hat folgende Diskrepanz an EINER BESTIMMTEN ZEILE festgestellt:

Dateiname: {filename}
Betroffene Zeile (Nummer): {target_line_number}
Widerspruch: {contradiction_summary}
Beschreibender Verbesserungsvorschlag des Reviewers: {suggested_update}

Kontext-Ausschnitt um die betroffene Zeile (mit Zeilennummern, Format "N: Inhalt"):
---BEGINN AUSSCHNITT---
{numbered_context_text}
---ENDE AUSSCHNITT---

Tatsächlicher, aktueller Gesamtprojektstand (zur Orientierung, NICHT Teil des zu erzeugenden Texts):
{current_project_concept}

Ändere AUSSCHLIESSLICH Zeile {target_line_number} (und höchstens 1-2 direkt logisch zusammenhängende Nachbarzeilen, falls die Aussage über mehrere Zeilen geht). ALLE anderen Zeilen im Ausschnitt bleiben BUCHSTABENGETREU unverändert."""

CONSTRAINTS = """Wichtige Einschränkungen:
- Gib den GESAMTEN Ausschnitt zurück (alle Zeilen des Kontexts), NICHT nur die geänderte Zeile -- aber alle unveränderten Zeilen müssen ZEICHENGENAU identisch zum Original bleiben.
- Ändere NUR Zeile {target_line_number} und ggf. direkt logisch zusammenhängende Nachbarzeilen. Ändere KEINE anderen Zeilen, auch wenn sie ähnlich aussehen.
- Erfinde KEINE Fakten, die nicht im "tatsächlichen Projektstand" oben belegt sind.
- Behalte Formatierung bei (Tabellen-Pipe-Zeichen, Einrückung, Markdown-Syntax).
- Verändere KEINE Zeilenumbrüche oder Leerzeilen, außer der Wortinhalt der Zielzeile selbst ändert sich.
- Falls die Zielzeile einen Status "Abgeschlossen" enthält, darf er NIE rückwärts auf "Offen" gesetzt werden.
- Gib NICHT die Zeilennummern-Präfixe ("N: ") im updated_context_text zurück -- nur den reinen Zeileninhalt.
{rejection_examples_block}"""

OUTPUT_FORMAT = """Antworte ausschließlich mit einem JSON-Objekt exakt in dieser Struktur:

{
  "updated_context_text": "der korrigierte Ausschnitt, ALLE Zeilen, OHNE Zeilennummern-Präfixe, mit \\n für Zeilenumbrüche",
  "change_summary": "1 Satz, was konkret an welcher Zeile geändert wurde"
}"""


@dataclass(frozen=True)
class ProposalWriterPromptComponents:
    role: str = ROLE
    task_template: str = TASK_TEMPLATE
    constraints: str = CONSTRAINTS
    output_format: str = OUTPUT_FORMAT


def build_proposal_writer_prompt(
    filename: str,
    target_line_number: int,
    numbered_context_text: str,
    contradiction_summary: str,
    suggested_update: str,
    current_project_concept: str,
    rejection_examples: list[str] | None = None,
    components: ProposalWriterPromptComponents | None = None,
) -> str:
    components = components or ProposalWriterPromptComponents()

    task = components.task_template.format(
        filename=filename,
        target_line_number=target_line_number,
        numbered_context_text=numbered_context_text,
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

    constraints = components.constraints.format(
        target_line_number=target_line_number, rejection_examples_block=rejection_block
    )

    return "\n\n".join([components.role, task, constraints, components.output_format])
