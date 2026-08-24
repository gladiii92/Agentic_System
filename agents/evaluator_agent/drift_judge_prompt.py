"""
agents/evaluator_agent/drift_judge_prompt.py

VERSION 2 (2026-08-24, grundlegender Umbau auf zeilengenaue Lokalisierung
-- siehe Chat-Verlauf: Nutzer-Anforderung, EXAKTE betroffene Zeilen zu
identifizieren statt grobe Abschnitte per Wortueberlappung zu raten).

AENDERUNG GEGENUEBER VERSION 1: Der Judge bekommt den Dateiinhalt jetzt
MIT ZEILENNUMMERN versehen und liefert eine LISTE von Einzelbefunden,
jeweils mit exakter Zeilennummer, statt eines einzelnen has_drift/
contradiction_summary-Paars. Das macht die nachgelagerte Lokalisierung
(line_context_extractor.py) deterministisch statt heuristisch-geraten.

Grund fuer diesen Umbau (siehe Chat-Verlauf): die bisherige Abschnitts-
Lokalisierung per Wortueberlappung waehlte zweimal den falschen Bereich
im Dokument, weil thematisch aehnliche Woerter in mehreren Abschnitten
vorkommen. Mit exakten Zeilennummern entfaellt dieses Rate-Problem
vollstaendig.
"""

from __future__ import annotations

from dataclasses import dataclass

ROLE = """Du bist ein erfahrener Technical Writer und Projektmanager. Du prüfst zeilengenau, ob ein Vault-Dokument noch inhaltlich zum tatsächlichen, aktuellen Stand eines Software-Projekts passt."""

TASK_TEMPLATE = """Vergleiche das folgende Vault-Dokument (mit Zeilennummern versehen) mit dem tatsächlichen, aktuellen Gesamtprojektstand.

Dateiname: {filename}

Vollständiger Inhalt des Vault-Dokuments, JEDE Zeile mit Zeilennummer (Format "N: Inhalt"):
{numbered_document_text}

Tatsächlicher, aktueller Gesamtprojektstand (aus frischem Code-/Vault-Scan):
{current_project_concept}

Zusätzlicher Kontext -- neuere Arbeitsprotokolle (Worklogs), die zeitlich NACH diesem Dokument entstanden sind und den tatsächlichen Fortschritt zeigen:
{recent_worklog_summaries}

Finde ALLE Stellen (nicht nur die erste!) in dem Dokument, an denen eine ZEILE einen Projektstatus, eine Phase, einen Fertigstellungsgrad oder eine geplante vs. bereits umgesetzte Funktion behauptet, die dem tatsächlichen Stand laut den Worklogs/dem Gesamtprojektstand widerspricht ODER eine offene Handlungsaufforderung enthält, die jetzt laut Projektstand erledigt werden kann."""

CONSTRAINTS = """Wichtige Einschränkungen:
- Bewerte NUR auf Basis der oben gegebenen Texte. Spekuliere NICHT über Informationen, die dort nicht enthalten sind.
- Eine andere Formulierung derselben Aussage ist KEIN Widerspruch.
- Gib fuer JEDEN gefundenen Einzelbefund die EXAKTE Zeilennummer an, an der die widersprüchliche/veraltete Aussage steht (die Zeilennummer aus dem "N:"-Präfix, nicht geschätzt).
- Wenn mehrere aufeinanderfolgende Zeilen zusammen EINE Aussage bilden (z.B. eine mehrzeilige Tabellenzeile), gib die Zeilennummer der ERSTEN betroffenen Zeile an.
- Wenn du unsicher bist, ob ein Widerspruch besteht, stufe severity als LOW ein statt zu raten, oder lasse den Befund ganz weg.
- Wenn KEIN Widerspruch gefunden wird, gib eine leere findings-Liste zurück.
- Antworte ausschließlich mit validem JSON, kein Freitext davor oder danach."""

OUTPUT_FORMAT = """Antworte ausschließlich mit einem JSON-Objekt exakt in dieser Struktur:

{
  "findings": [
    {
      "line_number": 42,
      "reasoning": "kurze Begründung, 1-2 Sätze, BEVOR du zum Urteil kommst",
      "severity": "LOW" | "MEDIUM" | "HIGH",
      "contradiction_summary": "was genau widerspricht sich an dieser Zeile, 1 Satz",
      "suggested_update": "konkreter Vorschlag, wie GENAU DIESE ZEILE angepasst werden sollte"
    }
  ]
}

Falls keine Widersprüche gefunden werden, gib {"findings": []} zurück."""


@dataclass(frozen=True)
class DriftJudgePromptComponents:
    role: str = ROLE
    task_template: str = TASK_TEMPLATE
    constraints: str = CONSTRAINTS
    output_format: str = OUTPUT_FORMAT


def number_lines(text: str) -> str:
    """Versieht jede Zeile mit einer 1-basierten Zeilennummer im Format
    'N: Inhalt'. 1-basiert, weil das fuer einen Menschen/Judge intuitiver
    ist als 0-basiert und leichter mit einem Text-Editor abzugleichen."""
    lines = text.splitlines()
    return "\n".join(f"{i + 1}: {line}" for i, line in enumerate(lines))


def build_drift_judge_prompt(
    filename: str,
    numbered_document_text: str,
    current_project_concept: str,
    recent_worklog_summaries: str,
    components: DriftJudgePromptComponents | None = None,
) -> str:
    """Args:
    numbered_document_text: Ergebnis von number_lines() ueber den VOLLEN
        Dateitext (nicht nur eine Zusammenfassung!) -- Aenderung gegenueber
        Version 1, die nur die Ollama-Zusammenfassung erhielt. Der Judge
        braucht jetzt den echten Text, um echte Zeilennummern liefern zu
        koennen.
    """
    components = components or DriftJudgePromptComponents()
    task = components.task_template.format(
        filename=filename,
        numbered_document_text=numbered_document_text,
        current_project_concept=current_project_concept,
        recent_worklog_summaries=recent_worklog_summaries or "(keine neueren Worklogs vorhanden)",
    )
    return "\n\n".join([components.role, task, components.constraints, components.output_format])
