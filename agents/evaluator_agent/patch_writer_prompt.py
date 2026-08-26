"""
agents/evaluator_agent/patch_writer_prompt.py

VERSION 2 (2026-08-26, Vollkontext-Ergaenzung -- siehe Chat-Verlauf).

Aenderung gegenueber der Version vom 2026-08-25: TASK_TEMPLATE bekommt
einen neuen Platzhalter {full_document_text} und die Aufgabenstellung
wurde umformuliert. Grund (realer Testfall ROADMAP.md, 2026-08-26):

Die alte Version wies das Modell an, exact_old_text ZWINGEND aus den
"+"-Zeilen DES HUNKS zu waehlen. Der Hunk zeigte nur den Satz "Alle
Phasen sind abgeschlossen UND das Projekt ist FERTIG!" -- die Zeile, die
den WIDERSPRUCH dazu enthaelt (Tabellenzeile "Phase 8 ... Offen ...
Phase 8 wurde am 2026-08-24 abgeschlossen"), stand an einer ANDEREN
Stelle im Dokument, ausserhalb des Hunks. Das Modell hat sich REGELKONFORM
verhalten (exact_old_text kam wortwoertlich aus dem Hunk), aber die Regel
selbst zwang es auf die falsche Zielzeile -- es hat die Tabellenzeile
verstuemmelt, weil es nicht wusste, dass DAS die eigentlich fehlerhafte
Stelle war, sondern nur den kontradiktorischen Satz kannte.

NEU: das Modell bekommt jetzt den vollen aktuellen Dokumenttext und darf
exact_old_text aus JEDER Stelle im Dokument waehlen, die tatsaechlich zum
Widerspruch gehoert -- nicht mehr zwingend aus dem Hunk selbst. Der Hunk
bleibt der Ausloeser/Beleg fuer den Widerspruch, aber die zu korrigierende
Stelle kann auch anderswo im Dokument liegen (z.B. eine veraltete
Tabellenzeile, die dem neuen Satz widerspricht).
"""

from __future__ import annotations

from dataclasses import dataclass

ROLE = """Du bist ein präziser Technical Writer. Du formulierst einen MINIMALEN Textersatz für eine bereits identifizierte, fachlich falsche Textstelle."""

TASK_TEMPLATE = """Folgende Textstelle wurde als fachlich nicht mehr korrekt identifiziert:

Dateiname: {filename}
Widerspruch: {contradiction_summary}

Die Änderung, die diesen Widerspruch AUSGELÖST hat (- = alter Text, + = aktuell im Dokument stehender Text, ohne Präfix = unveränderter Kontext):
{hunk_diff_text}

Vollständiger aktueller Text der Datei (durchsuche diesen Text, um die tatsächlich zu korrigierende Stelle zu finden -- das kann die oben gezeigte Änderung selbst sein, ODER eine ANDERE Stelle im Dokument, die dem neuen Text widerspricht, z.B. eine veraltete Tabellenzeile):
{full_document_text}

Tatsächlicher, aktueller Gesamtprojektstand (zur Orientierung):
{current_project_concept}

Identifiziere den EXAKTEN, wortwörtlichen Textausschnitt aus dem vollständigen Dokumenttext oben, der korrigiert werden muss, damit der Widerspruch behoben ist, und liefere einen präzisen Ersatztext dafür. Wähle dabei GENAU DIE Stelle, die tatsächlich fachlich falsch ist -- das ist nicht automatisch die oben gezeigte Änderung selbst, sondern kann auch die Stelle sein, der die Änderung widerspricht."""

CONSTRAINTS_TEMPLATE = """Wichtige Einschränkungen:
- exact_old_text MUSS ein WORTWÖRTLICHES, ZEICHENGENAUES Zitat aus dem vollständigen Dokumenttext oben sein -- keine Paraphrase, keine Korrektur von Tippfehlern im Original, exakt wie dort geschrieben (inklusive Leerzeichen, Satzzeichen, Zeilenumbrüche).
- exact_old_text soll so KURZ wie möglich sein, aber lang genug, um eindeutig zu sein (nicht nur ein einzelnes häufiges Wort).
- replacement_text ersetzt NUR exact_old_text -- ändere darin NICHTS, was nicht durch den Widerspruch begründet ist.
- Erfinde KEINE Fakten, die nicht im "tatsächlichen Projektstand" oder im vollständigen Dokumenttext oben belegt sind.
- Ändere KEINE Formatierung (Sprache, Wortwahl in Nachbarsätzen, Tabellensyntax), die nicht Teil des Widerspruchs ist.
- Falls ein Status bereits "Abgeschlossen" war, darf er NIE rückwärts auf "Offen" gesetzt werden.
- Lösche KEINE Information ohne Ersatz (z.B. keine Tabellenspalte einfach leeren) -- wenn eine Spalte/Zeile falsch ist, korrigiere ihren Inhalt, statt ihn zu entfernen.
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
    full_document_text: str,
    rejection_examples: list[str] | None = None,
    components: PatchWriterPromptComponents | None = None,
) -> str:
    components = components or PatchWriterPromptComponents()

    task = components.task_template.format(
        filename=filename,
        contradiction_summary=contradiction_summary,
        hunk_diff_text=hunk_diff_text,
        full_document_text=full_document_text or "(kein Volltext verfuegbar)",
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
