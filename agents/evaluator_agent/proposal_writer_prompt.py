"""
agents/evaluator_agent/proposal_writer_prompt.py

VERSION 3 (2026-08-24, Praezisions-Fix nach zweitem realen Testfehler --
siehe Chat-Verlauf): Version 2 loeste das Beschaedigungs-Problem (siehe
Version-2-Docstring), aber ein zweiter Testlauf zeigte einen SUBTILEREN
Fehler: das Modell verallgemeinerte einen konkreten Einzelbefund ("Phase 3
sollte abgeschlossen sein") auf ALLE offenen Phasen im Abschnitt ("Phase
3 BIS 8 abgeschlossen"), ohne fuer jede einzelne einen Beleg im
Projektstand zu haben -- UND entfernte dabei ungefragt Absatz-Umbrueche
in unbeteiligten Merkposten-Texten.

FIX: Der Prompt verlangt jetzt explizit eine BEGRUENDUNG PRO EINZELNER
ZEILE/AUSSAGE, die geaendert wird (nicht nur eine pauschale change_summary),
und verbietet explizit "Alles-oder-Nichts"-Aenderungen an Tabellenzeilen,
die nicht individuell belegt sind. Zusaetzlich: explizites Verbot,
Zeilenumbrueche/Absatzstruktur in unbeteiligten Teilen zu veraendern.
"""

from __future__ import annotations

from dataclasses import dataclass

ROLE = """Du bist ein erfahrener, sehr präziser Technical Writer. Du aktualisierst EINEN einzelnen Abschnitt eines Markdown-Dokuments MINIMAL-INVASIV, basierend auf einer bereits getroffenen fachlichen Einschätzung. Du änderst NUR das, was konkret belegt ist -- niemals mehr."""

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

Gehe JEDE Zeile/Tabellenzeile im Abschnitt einzeln durch. Ändere eine Zeile NUR, wenn der "tatsächliche Gesamtprojektstand" oben EXPLIZIT und KONKRET belegt, dass genau diese Zeile falsch ist. Wenn du für eine Zeile keinen konkreten Beleg hast, lasse sie UNVERÄNDERT -- auch wenn benachbarte Zeilen geändert werden."""

CONSTRAINTS_TEMPLATE = """Wichtige Einschränkungen:
- Gib AUSSCHLIESSLICH den Text für DIESEN EINEN Abschnitt zurück, beginnend mit der Überschrift-Zeile.
- Gib NICHT die ganze Datei, NICHT andere Abschnitte, NICHT den obigen Projektstand-Text zurück.
- Erfinde KEINE Fakten, die nicht im "tatsächlichen Projektstand" oben belegt sind.
- KEIN "Alles-oder-Nichts": wenn eine Tabelle mehrere Zeilen hat und nur EINE Zeile konkret belegt falsch ist, ändere NUR diese eine Zeile. Die anderen Zeilen bleiben exakt wie im Original, auch wenn sie thematisch ähnlich aussehen.
- Verändere NIEMALS Zeilenumbrüche, Absatzgrenzen oder Formatierung in Textteilen, die NICHT direkt vom Widerspruch betroffen sind. Wenn ein Absatz im Original über mehrere Zeilen umgebrochen ist, bleibt er das auch im Ergebnis, außer der Wortinhalt dieses konkreten Absatzes wird geändert.
- Falls eine Phase laut Original bereits "Abgeschlossen" war, darf der Status NIE rückwärts auf "Offen" gesetzt werden.
- Wenn du unsicher bist, ob eine Änderung an einer bestimmten Zeile belegt ist: lasse die Zeile UNVERÄNDERT. Im Zweifel keine Änderung statt einer unbelegten Änderung.
{rejection_examples_block}"""

OUTPUT_FORMAT = """Antworte ausschließlich mit einem JSON-Objekt exakt in dieser Struktur:

{
  "updated_section_text": "der korrigierte Text NUR dieses Abschnitts, mit \\n für Zeilenumbrüche",
  "changed_lines": ["Liste der konkret geänderten Zeilen/Aussagen, je mit kurzer Begründung, warum genau diese Zeile durch den Projektstand belegt ist"],
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
