"""
agents/evaluator_agent/proposal_writer_prompt.py

Vierter Prompt-Baustein (nach drift_judge_prompt.py). Zweck: aus dem
beschreibenden suggested_update-Text des Drift-Judges (Schicht 3) einen
KONKRETEN, direkt einsetzbaren neuen Volltext fuer das betroffene Vault-
Dokument erzeugen -- Option A aus dem Chat-Verlauf 2026-08-24: das System
soll die Aenderung tatsaechlich SELBST formulieren, nicht nur beschreiben,
damit spaeter (nach ausreichender Verifizierung durch den Nutzer) ein
Schreiben ohne Human-in-the-Loop denkbar wird.

WICHTIG -- Few-Shot-Lernen aus Ablehnungen (siehe Chat-Verlauf 2026-08-24):
Dieser Prompt bekommt optional eine Liste frueherer, vom Nutzer
ABGELEHNTER Vorschlaege mit Ablehnungsgrund als Few-Shot-Beispiele
mitgegeben (siehe rejection_history.py). Das ist BEWUSST kein Modell-
Finetuning (siehe Chat-Diskussion: zu wenig Datenvolumen, zu invasiv),
sondern ein wachsender, kuratierter Beispiel-Datensatz direkt im Prompt --
das etablierte "trace -> human review -> dataset -> re-run"-Muster aus
der Phase-0-Recherche (Handover-Dokument, Abschnitt 4.3).
"""

from __future__ import annotations

from dataclasses import dataclass

ROLE = """Du bist ein erfahrener Technical Writer. Du formulierst konkrete, direkt einsetzbare Aktualisierungen für Dokumente einer internen Projekt-Wissensdatenbank (Obsidian-Vault), basierend auf einer bereits getroffenen fachlichen Einschätzung."""

TASK_TEMPLATE = """Ein Reviewer hat folgende Diskrepanz zwischen einem Vault-Dokument und dem tatsächlichen Projektstand festgestellt:

Dateiname: {filename}
Widerspruch: {contradiction_summary}
Beschreibender Verbesserungsvorschlag des Reviewers: {suggested_update}

Aktueller, vollständiger Inhalt der Datei:
{original_full_text}

Tatsächlicher, aktueller Gesamtprojektstand:
{current_project_concept}

Erzeuge den VOLLSTÄNDIGEN, korrigierten Text der gesamten Datei. Übernimm alle Teile, die laut Widerspruch nicht betroffen sind, UNVERÄNDERT (exaktes Markdown-Format, Tabellen, Überschriften). Ändere NUR die Stellen, die dem festgestellten Widerspruch entsprechen."""

CONSTRAINTS_TEMPLATE = """Wichtige Einschränkungen:
- Gib den GESAMTEN Dateiinhalt zurück, nicht nur den geänderten Ausschnitt.
- Erfinde KEINE Fakten, die nicht im "tatsächlichen Projektstand" oben belegt sind.
- Behalte Formatierung, Struktur und Stil des Originals so weit wie möglich bei.
- Ändere nur, was durch den Widerspruch begründet ist -- keine unnötigen Umformulierungen anderer Abschnitte.
{rejection_examples_block}"""

OUTPUT_FORMAT = """Antworte ausschließlich mit einem JSON-Objekt exakt in dieser Struktur:

{
  "updated_full_text": "der komplette neue Dateiinhalt als einzelner String, mit \\n für Zeilenumbrüche",
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
    contradiction_summary: str,
    suggested_update: str,
    original_full_text: str,
    current_project_concept: str,
    rejection_examples: list[str] | None = None,
    components: ProposalWriterPromptComponents | None = None,
) -> str:
    """Baut den finalen Prompt. rejection_examples ist eine Liste bereits
    fertig formatierter Few-Shot-Text-Bloecke (siehe rejection_history.py,
    format_for_prompt()) -- dieses Modul kennt das Speicherformat der
    Ablehnungs-Historie bewusst NICHT, um die Kopplung locker zu halten."""
    components = components or ProposalWriterPromptComponents()

    task = components.task_template.format(
        filename=filename,
        contradiction_summary=contradiction_summary,
        suggested_update=suggested_update,
        original_full_text=original_full_text,
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
