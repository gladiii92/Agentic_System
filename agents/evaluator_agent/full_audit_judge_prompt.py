"""
agents/evaluator_agent/full_audit_judge_prompt.py

NEU (2026-08-27): Spezial-Prompt für Full-Audit-Prüfungen.

Im Gegensatz zu drift_judge_prompt.py (bewertet eine lokale Änderung auf
Belegtheit) bewertet dieser Prompt einen gesamten Dokumentabschnitt auf
INTERNE KONSISTENZ -- sucht aktiv nach Widersprüchen zwischen verschiedenen
Teilen des Abschnitts ODER zwischen Abschnitt und Volltext.

Verwendung: run_full_audit.py übergibt chunk_text als document_section_to_evaluate
(kein hunk_diff_text), und dieser Prompt wird verwendet statt drift_judge_prompt.py.
"""

from __future__ import annotations

from dataclasses import dataclass

ROLE = """Du bist ein erfahrener Technical Writer und Projektmanager. Du prüfst einen Dokumentabschnitt auf INTERNE KONSISTENZ -- du suchst aktiv nach Widersprüchen zwischen verschiedenen Teilen des Abschnitts ODER zwischen Abschnitt und Volltext."""

TASK_TEMPLATE = """Folgender Dokumentabschnitt wird auf Konsistenz geprüft:

Dateiname: {filename}

Dokumentabschnitt (zu prüfender Ausschnitt):
{document_section_to_evaluate}

Vollständiger aktueller Text derselben Datei (Referenz für abteilungsübergreifende Widersprüche):
{full_document_text}

Tatsächlicher, aktueller Gesamtprojektstand (aus frischem Code-/Vault-Scan):
{current_project_concept}

Zusätzlicher Kontext -- Zusammenfassungen anderer Dokumente im selben Projekt:
{recent_worklog_summaries}

Aufgabe: Prüfe diesen Dokumentabschnitt explizit auf Widersprüche:
1. Gibt es Widersprüche INNERHALB des Abschnitts (z.B. Tabelle sagt "Phase 3: Offen", Text sagt "Phase 3 ist abgeschlossen")?
2. Gibt es Widersprüche ZWISCHEN Abschnitt und Volltext (z.B. Abschnitt sagt "Phase 8: Abgeschlossen", andere Stelle im Volltext sagt "Phase 8: Offen")?
3. Gibt es Widersprüche zwischen Dokument und Projektstand (z.B. Dokument sagt "Phase 7: Abgeschlossen", Worklogs sagen "Phase 7: In Arbeit")?

Melde JEDE gefundene Inkonsistenz als is_supported=false, auch wenn keine lokale Änderung vorliegt."""

CONSTRAINTS = """Wichtige Einschränkungen:
- Suche AKTIV nach Widersprüchen -- bewerte nicht nur, ob der Text "belegt" ist.
- Eine fehlende oder unvollständige "Status:"/"Erreicht:"-Angabe INNERHALB des Abschnitts einer einzelnen Phase/Funktion ist für sich allein KEIN Beleg dafür, dass ein an anderer Stelle (z.B. einer Gesamtstatus-Tabelle) genannter Status FALSCH ist. Fehlende Binnendokumentation ist eine Dokumentationslücke, kein inhaltlicher Widerspruch. Setze in diesem Fall is_supported=true UND ergänze im Feld "reasoning" den Hinweis, dass die Binnendokumentation dieser Phase unvollständig ist -- aber melde es NICHT als is_supported=false, solange keine AKTIV widersprechende Aussage (z.B. eine andere Tabelle mit einem anderen Status) vorliegt.
- Eine knappe Status-Angabe in einer Gesamtstatus-Tabelle (z.B. "Abgeschlossen (2026-08-24)" ohne Auflistung der einzelnen umgesetzten Punkte) ist KEIN Widerspruch zu einem detaillierteren "Erreicht:"-Block im Phasenabschnitt oder zu einem zusammenfassenden Satz im Dokument -- die Tabelle dient der Übersicht, der "Erreicht:"-Block der Detailnachweise. Setze is_supported=true, wenn der Tabellenstatus mit dem Phasenstatus oder dem zusammenfassenden Satz übereinstimmt, auch wenn die Tabelle weniger Details nennt.
- Unterschiedliche Datumsangaben (z.B. "Abgeschlossen (2026-08-24)" in der Tabelle vs. "Alle Phasen bis Phase 8 sind abgeschlossen (25.08.2026)" im Fazit) sind KEIN Widerspruch, solange der STATUS-WERT (z.B. "Abgeschlossen") identisch ist. Das Datum kann sich durch spätere Präzisierung ändern, der Status bleibt gleich. Setze in diesem Fall is_supported=true.
- ABER: Wenn der STATUS-WERT selbst widersprüchlich ist (z.B. Tabelle sagt "Phase 3: Nächster Schritt", Fazit sagt "Alle Phasen bis Phase 8 sind abgeschlossen"), ist das ein ECHTER Widerspruch -- setze is_supported=false, severity=MEDIUM/HIGH.
- "is_supported=false" bedeutet: der Dokumentabschnitt oder der Volltext enthält eine Aussage, die einer anderen Aussage im selben Dokument, dem Projektstand oder den anderen Dokumenten AKTIV UND KONKRET widerspricht.
- "is_meaningful=false" bedeutet: der Abschnitt enthält keine bewertbaren Aussagen (z.B. nur Formatierung, leere Zeilen, reine Überschriften ohne Inhalt).
- Antworte ausschließlich mit validem JSON, kein Freitext davor oder danach."""

SEVERITY_GUIDANCE = """SEVERITY-EINSTUFUNG (bitte genau befolgen):
- HIGH: Der Abschnitt enthält einen GESAMTPROJEKTSTATUS (z.B. "alles fertig", "Projekt abgeschlossen"), der durch den Rest des Dokuments, die Worklogs oder andere Dokumente EINDEUTIG UND UMFASSEND widerlegt wird (mehrere offene Phasen).
- MEDIUM: Der Abschnitt enthält den Status EINER EINZELNEN, KONKRET BENANNTEN Phase/Funktion, der eindeutig widerlegt wird.
- LOW: Der Abschnitt enthält eine Nuance, die nicht ganz präzise ist, aber nur schwach belegt widerlegt wird, oder die Belege sind nur indirekt."""

OUTPUT_FORMAT = """Antworte ausschließlich mit einem JSON-Objekt exakt in dieser Struktur:

{
"is_meaningful": true,
"is_supported": false,
"severity": "MEDIUM",
"reasoning": "kurze Begründung, 2-3 Sätze, benenne explizit die widersprüchlichen Stellen (z.B. 'Tabelle Zeile X sagt Phase 3: Nächster Schritt, Fazit Zeile Y sagt Alle Phasen bis Phase 8 sind abgeschlossen')",
"contradiction_summary": "falls is_supported=false: was genau widerspricht sich (z.B. 'Phase 3 Status: Tabelle vs. Fazit'). Sonst leerer String."
}"""

@dataclass(frozen=True)
class FullAuditJudgePromptComponents:
    role: str = ROLE
    task_template: str = TASK_TEMPLATE
    constraints: str = CONSTRAINTS
    severity_guidance: str = SEVERITY_GUIDANCE
    output_format: str = OUTPUT_FORMAT

def build_full_audit_judge_prompt(
    filename: str,
    document_section_to_evaluate: str,
    current_project_concept: str,
    recent_worklog_summaries: str,
    full_document_text: str,
    components: FullAuditJudgePromptComponents | None = None,
) -> str:
    components = components or FullAuditJudgePromptComponents()
    task = components.task_template.format(
        filename=filename,
        document_section_to_evaluate=document_section_to_evaluate or "(kein Abschnitt verfügbar)",
        full_document_text=full_document_text or "(kein Volltext verfügbar)",
        current_project_concept=current_project_concept or "(kein Projektstand verfügbar)",
        recent_worklog_summaries=recent_worklog_summaries or "(keine anderen Dokumente vorhanden)",
    )
    return "\n\n".join([components.role, task, components.constraints, components.severity_guidance, components.output_format])