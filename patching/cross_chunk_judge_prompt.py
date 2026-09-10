"""Prompt template for the Cross‑Chunk Audit Judge.

This judge receives a collection of Evidence objects (one per chunk) and
determines whether any of them constitute a genuine contradiction when
considered together.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CrossChunkJudgePromptComponents:
    """Components required to build the cross‑chunk judge prompt."""

    role: str = """Du bist ein Experte für die Überprüfung von Dokumentenkonflikten. Dein Job ist es,
    zu erkennen, ob verschiedene Teile eines Dokuments widersprüchliche Aussagen enthalten."""

    task_template: str = """
    Zu prüfende Evidence-Aussagen aus unterschiedlichen Chunks derselben Datei.
    Jede Aussage ist mit ihrer Quelle gekennzeichnet:

      [STATUS]          = allgemeine Statusangabe (z.B. Dokument-Status)
      [PHASENABSCHNITT] = Status im Abschnitt einer einzelnen Phase ('Status:'-Zeile)
      [TABELLE]         = Zeile der Gesamtstatus-Tabelle
      [GESAMTAUSSAGE]   = zusammenfassende Globalaussage (z.B. Fazit-Satz wie 'Alle Phasen ... abgeschlossen')
      [MERKPOSTEN]      = offener Punkt / Merkposten / TODO / Wiedervorlage

    {evidence_items}

    Aufgabe:
    1. Gibt es zwischen zwei konkreten Evidence-Aussagen einen logischen Widerspruch?
    2. Sind zwei Aussagen nur unterschiedlich formuliert, aber semantisch identisch?
    3. Gibt es nur fehlende Informationen, Vermutungen oder unvollständige Abschnitte?
    """

    constraints: str = """
    - Bewerte NUR die gelieferten Evidence-Aussagen.
    - Ein Widerspruch muss durch zwei konkrete Evidence-Aussagen belegbar sein.

    DATUMS-RANGFOLGE (wichtigste Regel, bitte genau befolgen):
    - Enthält eine Evidence-Aussage ein konkretes Datum, z.B. in Klammern "(2026-08-24)"
      oder "(25.08.2026)" oder den Zusatz "(Stand: JJJJ-MM-TT)", so ist die Aussage mit
      dem NEUESTEN Datum die maßgebliche Quelle der Wahrheit.
    - Steht eine ältere datierte oder undatierte Aussage im Widerspruch zur neuesten
      datierten Aussage, so ist das ein ECHTER Widerspruch (is_supported=false) -- die
      ältere/undatierte Aussage muss an die neueste datierte angeglichen werden.
    - Ohne widersprechende Aussagen mit neuem Datum gilt die bestehende Argumentation.

    STATUS-HIERARCHIE:
    - Die Statuswerte sind wie folgt geordnet:
      offen < nächster Schritt < in arbeit < abgeschlossen < abgeschlossen und real verifiziert
    - Zwei Aussagen, die auf derselben Hierarchie-Stufe liegen (z.B. "Abgeschlossen" vs.
      "Abgeschlossen und real verifiziert"), sind KEIN Widerspruch -- die zweite ist nur
      präziser/nachvollziehbarer. Setze in diesem Fall is_supported=true.
    - WICHTIG: "Offen" und "Nächster Schritt" sind KEIN Widerspruch zueinander -- beide
      bedeuten "noch nicht abgeschlossen" und liegen in derselben Bedeutungsklasse.
      Setze in diesem Fall is_supported=true.
    - Ein echter Widerspruch liegt vor, wenn Aussagen auf VERSCHIEDENEN Stufen stehen und
      sich widersprechen (z.B. "Offen" vs. "Abgeschlossen" für dieselbe Phase).

    KEINE WIDERSPRÜCHE (wie beim Drift-Judge):
    - Ein offener Punkt / Merkposten / TODO / "Offen: ..." ist NORMAL und KEIN Widerspruch,
      auch wenn eine übergeordnete Phase an anderer Stelle als abgeschlossen gilt.
    - Eine knappe Status-Angabe in einer Tabelle (z.B. "Abgeschlossen (2026-08-24)") ist
      KEIN Widerspruch zu einem detaillierteren "Erreicht:"-Block im Phasenabschnitt,
      wenn der Status-Wert auf derselben Hierarchie-Stufe liegt.
    - Unterschiedliche Datumsformate (z.B. "25.08." vs "2026-08-25") sind KEIN Widerspruch,
      wenn das Datum semantisch identisch ist. Unterschiedliche ECHTE Daten sind dagegen
      relevant für die Datums-Rangfolge oben.
    - Unterschiedliche Formulierungen/Synonyme sind KEIN Widerspruch, wenn sie dieselbe
      Aussage bedeuten.
    - Fehlende Informationen oder unvollständige Abschnitte sind KEIN Widerspruch.
    - Vermutungen sind KEIN Widerspruch.

    PRÜFREIHENFOLGE (bitte genau so vorgehen und den ersten Treffer melden):
    1. Zuerst [GESAMTAUSSAGE]-Aussagen gegen [TABELLE]-Aussagen prüfen (Globalaussage vs. Gesamtstatus-Tabelle). Ein Treffer hier ist VORRANGIG: melde DIESEN Widerspruch, auch wenn andere Stufen-Divergenzen existieren.
    2. Dann [TABELLE]-Aussagen gegen [PHASENABSCHNITT]-Aussagen derselben Phase prüfen (gleiche Phasennummer).
    3. Erst danach verbleibende Einzelpaare prüfen, wenn die Schritte 1-2 keinen Treffer ergaben.

    - "is_supported=false" bedeutet: Es GIBT einen aktiven, belegbaren Widerspruch zwischen den Evidence-Aussagen.
    - "is_supported=true" bedeutet: Es gibt KEINEN aktiven Widerspruch zwischen den Evidence-Aussagen.
    - "is_meaningful=true" bedeutet: Die Evidence-Aussagen sind inhaltlich relevant genug, um geprüft zu werden. Setze bei echten Widersprüchen (is_supported=false) auch is_meaningful=true.
    """

    output_format: str = """
    Antworte ausschließlich mit einem JSON-Objekt exakt in dieser Struktur:

    {
        "is_meaningful": true,
        "is_supported": false,
        "severity": "HIGH",
        "reasoning": "kurze Begründung, 2-3 Sätze. Benenne die zwei konkreten Evidence-Aussagen (mit ihren Kategorien).",
        "contradiction_summary": "was genau widerspricht sich. Benenne beide Aussagen mit Zeile und Kategorie. Sonst leerer String."
    }
    """


def build_cross_chunk_judge_prompt(
    evidence_items: list[str],
    components: CrossChunkJudgePromptComponents | None = None,
) -> str:
    """Build the full prompt for the cross‑chunk judge."""
    components = components or CrossChunkJudgePromptComponents()
    task = components.task_template.format(evidence_items="\n".join(f"- {item}" for item in evidence_items))
    return "\n\n".join([components.role, task, components.constraints, components.output_format])