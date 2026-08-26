"""
agents/evaluator_agent/patch_writer_prompt.py

VERSION 3 (2026-08-26, Standardregel "Hunk-Zeile ist Korrekturziel" --
siehe Chat-Verlauf).

Aenderung gegenueber Version 2 (Vollkontext-Ergaenzung, selbes Datum):
Version 2 erlaubte dem Modell, JEDE Stelle im Volltext als Korrekturziel
zu waehlen, ohne Praeferenz. In mehreren realen Testlaeufen (ROADMAP.md,
Phase-3-Status-Widerspruch) fuehrte das reproduzierbar dazu, dass das
Modell eine ANDERE, thematisch aehnliche Zeile (z.B. ein separates
"Status:"-Feld an anderer Stelle im Dokument) aenderte, statt die im
Hunk selbst gezeigte Zeile zu korrigieren -- obwohl GENAU DIESE Zeile
die vom Nutzer bewusst herbeigefuehrte, fehlerhafte Aenderung war.

Kernproblem (siehe Chat-Verlauf): der Hunk zeigt die Aenderung, aber der
Prompt gab keine klare Regel, WANN der Hunk selbst das Korrekturziel ist
und wann eine andere Stelle. Neue Standardregel: der Hunk ist im
Regelfall SELBST das Korrekturziel (die im Hunk gezeigte Aenderung wird
auf einen durch den Volltext belegten korrekten Wert zurueckgesetzt).
Nur wenn der Widerspruch AUSDRUECKLICH nicht im Hunk selbst liegt,
sondern in einem SEPARATEN Satz, der durch die Hunk-Aenderung neu falsch
geworden ist (z.B. ein zusammenfassender Fazit-Satz, der durch die neue
Formulierung der Hunk-Zeile widersprochen wird), darf eine andere Stelle
gewaehlt werden.
"""

from __future__ import annotations

from dataclasses import dataclass

ROLE = """Du bist ein präziser Technical Writer. Du formulierst einen MINIMALEN Textersatz für eine bereits identifizierte, fachlich falsche Textstelle."""

TASK_TEMPLATE = """Folgende Textstelle wurde als fachlich nicht mehr korrekt identifiziert:

Dateiname: {filename}
Widerspruch: {contradiction_summary}

Die Änderung, die diesen Widerspruch AUSGELÖST hat (- = alter Text, + = aktuell im Dokument stehender Text, ohne Präfix = unveränderter Kontext):
{hunk_diff_text}

Vollständiger aktueller Text der Datei (NUR zur Orientierung -- um zu entscheiden, welcher Wert in der Hunk-Zeile korrekt ist, und um im Ausnahmefall eine andere betroffene Stelle zu finden):
{full_document_text}

Tatsächlicher, aktueller Gesamtprojektstand (zur Orientierung):
{current_project_concept}

STANDARDREGEL (befolge diese, außer der Ausnahmefall unten trifft klar zu):
Die zu korrigierende Stelle ist im Regelfall GENAU die oben im Hunk gezeigte "+"-Zeile selbst -- nicht eine andere, thematisch ähnliche Zeile irgendwo sonst im Dokument. Deine Aufgabe ist normalerweise: setze den Wert in DIESER Zeile auf den durch den vollständigen Dokumenttext belegten, korrekten Stand zurück (z.B. wenn die Hunk-Zeile "Abgeschlossen" behauptet, aber der Rest des Dokuments eindeutig zeigt, dass es noch offen ist, korrigiere GENAU DIESE Zeile zurück auf den korrekten Status).

AUSNAHMEFALL: Wähle NUR dann eine ANDERE Stelle als Korrekturziel, wenn der Widerspruch nachweislich NICHT in der Hunk-Zeile selbst liegt, sondern in einem separaten Satz an anderer Stelle im Dokument, der durch die neue Formulierung der Hunk-Zeile widersprüchlich geworden ist (z.B. ein übergeordneter Fazit-/Zusammenfassungssatz, der durch die Hunk-Änderung falsch wurde, während die Hunk-Zeile selbst unverändert korrekt bleiben soll)."""

CONSTRAINTS_TEMPLATE = """Wichtige Einschränkungen:
- exact_old_text MUSS ein WORTWÖRTLICHES, ZEICHENGENAUES Zitat aus dem vollständigen Dokumenttext oben sein -- keine Paraphrase, keine Korrektur von Tippfehlern im Original, exakt wie dort geschrieben (inklusive Leerzeichen, Satzzeichen, Zeilenumbrüche).
- exact_old_text soll so KURZ wie möglich sein, aber lang genug, um eindeutig zu sein (nicht nur ein einzelnes häufiges Wort).
- replacement_text ersetzt NUR exact_old_text -- ändere darin NICHTS, was nicht durch den Widerspruch begründet ist.
- Erfinde KEINE Fakten, die nicht im "tatsächlichen Projektstand" oder im vollständigen Dokumenttext oben belegt sind.
- Ändere KEINE Formatierung (Sprache, Wortwahl in Nachbarsätzen, Tabellensyntax), die nicht Teil des Widerspruchs ist.
- Falls ein Status bereits "Abgeschlossen" war, darf er NIE rückwärts auf "Offen" gesetzt werden.
- Lösche KEINE Information ohne Ersatz (z.B. keine Tabellenspalte einfach leeren) -- wenn eine Spalte/Zeile falsch ist, korrigiere ihren Inhalt, statt ihn zu entfernen.
- Bevor du eine ANDERE Zeile als die Hunk-Zeile wählst: pruefe nochmal, ob die Standardregel oben nicht doch zutrifft. Im Zweifel gilt die Standardregel (Hunk-Zeile korrigieren), nicht der Ausnahmefall.
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
