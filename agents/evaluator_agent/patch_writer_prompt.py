"""
agents/evaluator_agent/patch_writer_prompt.py

NEUES Modul (2026-08-25, ersetzt proposal_writer_prompt.py komplett).
Zwingt das Modell, AUSSCHLIESSLICH ein exact_old_text/replacement_text-
Paar zu liefern -- NIEMALS einen frei formulierten Volltext-Abschnitt
oder Zeilenausschnitt (siehe patch_models.py-Docstring fuer die
Sicherheitsbegruendung dieses Formats).

Das Modell bekommt NUR den bereits vom Judge als "nicht belegt" (is_supported
=false) markierten Hunk -- die kleinstmoegliche Aufgabe: "zitiere den Teil,
der falsch ist, wortwoertlich, und liefere einen Ersatztext dafuer."
"""

from __future__ import annotations

from dataclasses import dataclass

ROLE = """Du bist ein präziser Technical Writer. Du formulierst einen MINIMALEN Textersatz für eine bereits identifizierte, fachlich falsche Textstelle."""

TASK_TEMPLATE = """Folgende Textstelle wurde als fachlich nicht mehr korrekt identifiziert:

Dateiname: {filename}
Widerspruch: {contradiction_summary}

Die betroffene Textänderung im Dokument (- = alter Text, + = aktuell im Dokument stehender, zu korrigierender Text, ohne Präfix = unveränderter Kontext):
{hunk_diff_text}

Tatsächlicher, aktueller Gesamtprojektstand (zur Orientierung):
{current_project_concept}

Identifiziere den EXAKTEN, wortwörtlichen Textausschnitt (eine oder mehrere zusammenhängende Zeilen, beginnend und endend mit "+"-Zeilen aus dem Diff oben) aus dem AKTUELL im Dokument stehenden Text, der korrigiert werden muss, und liefere einen präzisen Ersatztext dafür."""

CONSTRAINTS_TEMPLATE = """Wichtige Einschränkungen:
- exact_old_text MUSS ein WORTWÖRTLICHES, ZEICHENGENAUES Zitat aus den "+"-Zeilen oben sein -- keine Paraphrase, keine Korrektur von Tippfehlern im Original, exakt wie dort geschrieben (inklusive Leerzeichen, Satzzeichen, Zeilenumbrüche).
- exact_old_text soll so KURZ wie möglich sein, aber lang genug, um eindeutig zu sein (nicht nur ein einzelnes häufiges Wort).
- replacement_text ersetzt NUR exact_old_text -- ändere darin NICHTS, was nicht durch den Widerspruch begründet ist.
- Erfinde KEINE Fakten, die nicht im "tatsächlichen Projektstand" oben belegt sind.
- Ändere KEINE Formatierung (Sprache, Wortwahl in Nachbarsätzen, Tabellensyntax), die nicht Teil des Widerspruchs ist.
- Falls ein Status bereits "Abgeschlossen" war, darf er NIE rückwärts auf "Offen" gesetzt werden.
{rejection_examples_block}"""

OUTPUT_FORMAT = """Antworte ausschließlich mit einem JSON-Objekt exakt in dieser Struktur:

{
  "exact_old_text": "wortwörtliches Zitat aus dem Dokument, das ersetzt werden soll",
  "replacement_text": "der neue, korrigierte Text",
  "change_summary": "1 Satz, was konkret geändert wurde"
}"""


@dataclass(frozen=True)
class PatchWriterPromptComponents:
    role: str = ROLE
    task_template: str = TASK_TEMPLATE
    constraints_template: str = CONSTRAINTS_TEMPLATE
    output_format: str = OUTPUT_FORMAT


def build_patch_writer_prompt(
    filename: str,
    contradiction_summary: str,
    hunk_diff_text: str,
    current_project_concept: str,
    rejection_examples: list[str] | None = None,
    components: PatchWriterPromptComponents | None = None,
) -> str:
    components = components or PatchWriterPromptComponents()

    task = components.task_template.format(
        filename=filename,
        contradiction_summary=contradiction_summary,
        hunk_diff_text=hunk_diff_text,
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
