"""
agents/evaluator_agent/full_audit_judge_prompt.py

Spezifischer Prompt für den Full-Audit-Modus. Sucht aktiv nach Widersprüchen
ausschließlich INNERHALB des gesamten Dokumenten-Chunks.
"""

from __future__ import annotations
from dataclasses import dataclass

ROLE = """Du bist ein erfahrener Technical Writer und Projektmanager. Dies ist ein Full-Audit, kein Diff-Review. Deine Aufgabe ist es, einen vorgegebenen Dokumentabschnitt (Chunk) aktiv auf inhaltliche Inkonsistenzen und Widersprüche ZU SICH SELBST zu prüfen."""

TASK_TEMPLATE = """Zu prüfender Dokumentabschnitt (Chunk) aus der Datei {filename}:

{document_section_to_evaluate}

Aufgabe: 
1. Gibt es innerhalb des gelieferten Chunks einen konkreten logischen Widerspruch?
2. Gibt es widersprüchliche aktive Statusangaben innerhalb des Chunks?
3. Gibt es eine explizite Aussage innerhalb des Chunks, die einer anderen expliziten Aussage desselben Chunks widerspricht?
"""

CONSTRAINTS = """Wichtige Einschränkungen:
- Bewerte AUSSCHLIESSLICH den Text innerhalb dieses Chunks.
- Ein Widerspruch muss durch zwei konkrete Textstellen im Chunk belegbar sein.

REGEL 0 -- GLEICHE HIERARCHIE-STUFE = KEIN WIDERSPRUCH:
- "Abgeschlossen" und "Abgeschlossen und real verifiziert" stehen auf derselben
  (höchsten) Stufe: die zweite Form ist nur präziser. Das ist NIEMALS ein
  Widerspruch. Setze is_supported=true.
- "Offen" und "Nächster Schritt" stehen ebenfalls in derselben Bedeutungsklasse
  ("noch nicht abgeschlossen") -- auch das ist KEIN Widerspruch.
- Beachte dies als ERSTES und bevor du irgendeinen Widerspruch meldest.

VERGLEICHE NUR INNERHALB DERSELBEN PHASE:
- Ein Widerspruch liegt nur vor, wenn sich zwei Aussagen auf DIESELBE Phase
  (gleiche Phasennummer) beziehen und dabei einen unterschiedlichen Gesamtstatus
  behaupten (z.B. dieselbe Phase einmal als "abgeschlossen" und einmal als "offen").
- Status-Angaben VERSCHIEDENER Phasen (z.B. Phase 2.5 vs. Phase 8) sind NIEMALS
  ein Widerspruch zueinander -- auch nicht wenn sie sich in der Genauigkeit
  unterscheiden.

DATUMS-RANGFOLGE (zweitwichtigste Regel, bitte genau befolgen):
- Enthält eine Aussage ein konkretes Datum, z.B. in Klammern "(2026-08-24)",
  "(25.08.2026)" oder den Zusatz "(Stand: JJJJ-MM-TT)", so ist die Aussage mit dem
  NEUESTEN Datum die maßgebliche Quelle der Wahrheit.
- Steht eine ältere datierte oder undatierte Aussage im Widerspruch zur neuesten
  datierten Aussage, so ist das ein ECHTER Widerspruch (is_supported=false) -- die
  ältere/undatierte Aussage muss an die neueste datierte angeglichen werden.

STATUS-HIERARCHIE:
- Die Statuswerte sind wie folgt geordnet:
  offen < nächster Schritt < in arbeit < abgeschlossen < abgeschlossen und real verifiziert
- Zwei Aussagen auf derselben Hierarchie-Stufe (z.B. "Abgeschlossen" vs.
  "Abgeschlossen und real verifiziert") sind KEIN Widerspruch -- die zweite ist nur
  präziser. Setze is_supported=true.
- Ein echter Widerspruch liegt vor, wenn Aussagen auf VERSCHIEDENEN Stufen stehen und
  sich widersprechen (z.B. "Offen" vs. "Abgeschlossen" für dieselbe Phase).
- "Offen" und "Nächster Schritt" sind KEIN Widerspruch zueinander (beide = noch
  nicht abgeschlossen). Setze is_supported=true.

KEINE WIDERSPRÜCHE:
- Ein offener Punkt / Merkposten / TODO / "Offen: ..." ist NORMAL und KEIN Widerspruch,
  auch wenn eine übergeordnete Phase als abgeschlossen gilt. Setze is_supported=true.
- Eine knappe Status-Angabe in einer Tabelle (z.B. "Abgeschlossen (2026-08-24)") ist
  KEIN Widerspruch zu einem detaillierteren "Erreicht:"-Block im Phasenabschnitt,
  wenn der Status-Wert auf derselben Hierarchie-Stufe liegt.
- Setze einen Status NIEMALS rückwärts von "Abgeschlossen"/"Abgeschlossen und real
  verifiziert" auf "Offen"/"Nächster Schritt", außer eine NEUERE datierte Aussage im
  selben Chunk belegt das ausdrücklich.
- Unterschiedliche Datumsformate (z.B. "25.08." vs "2026-08-25") sind KEIN Widerspruch, wenn das Datum semantisch identisch ist. Unterschiedliche ECHTE Daten sind dagegen relevant für die Datums-Rangfolge oben.
- Unterschiedliche Formulierungen/Synonyme sind KEIN Widerspruch, wenn sie dieselbe Aussage bedeuten.
- Fehlende Informationen oder unvollständige Abschnitte sind KEIN Widerspruch.
- Vermutungen sind KEIN Widerspruch.
- "is_supported=false" bedeutet: Es GIBT einen aktiven, belegbaren Widerspruch im Chunk.
- "is_supported=true" bedeutet: Es gibt KEINEN aktiven Widerspruch im Chunk.
- "is_meaningful=true" bedeutet: Der Chunk enthält inhaltlich relevante Aussagen, die geprüft wurden. Setze bei echten Widersprüchen (is_supported=false) auch is_meaningful=true.

SEVERITY-EINSTUFUNG (bitte genau befolgen):
- HIGH: Widerspruch betrifft den Gesamtstatus bzw. den Abschlussstatus des Projekts oder widerspricht einer zentralen Gesamtstatus-Aussage.
- MEDIUM: Widerspruch betrifft eine einzelne Phase, Funktion oder einen konkreten Projektbestandteil.
- LOW: kleinere, nicht-zentrale Inkonsistenz.

Antworte ausschließlich mit validem JSON, kein Freitext davor oder danach.
"""

OUTPUT_FORMAT = """Antworte ausschließlich mit einem JSON-Objekt exakt in dieser Struktur:

{
"is_meaningful": true,
"is_supported": false,
"severity": "HIGH",
"reasoning": "kurze Begründung, 2-3 Sätze. Benenne die zwei konkreten Textstellen im Chunk.",
"contradiction_summary": "falls is_supported=false: was genau widerspricht sich. Sonst leerer String."
}"""

@dataclass(frozen=True)
class FullAuditJudgePromptComponents:
    role: str = ROLE
    task_template: str = TASK_TEMPLATE
    constraints: str = CONSTRAINTS
    output_format: str = OUTPUT_FORMAT

def build_full_audit_judge_prompt(
    filename: str,
    document_section_to_evaluate: str,
    components: FullAuditJudgePromptComponents | None = None,
) -> str:
    components = components or FullAuditJudgePromptComponents()
    task = components.task_template.format(
        filename=filename,
        document_section_to_evaluate=document_section_to_evaluate,
    )
    return "\n\n".join([components.role, task, components.constraints, components.output_format])