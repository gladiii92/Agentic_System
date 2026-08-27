"""
agents/evaluator_agent/drift_judge_prompt.py

VERSION 5 (2026-08-26, Vollkontext-Ergaenzung -- siehe Chat-Verlauf:
Judge stufte einen eindeutigen Widerspruch zwischen einer Statustabelle
und einem Fazit-Satz IM SELBEN DOKUMENT als LOW/trivial ein, weil er nur
den isolierten Hunk (Aenderungsblock + wenige Kontextzeilen) sah, nicht
den Rest des Dokuments. Die Statustabelle, die dem neuen Satz widerspricht,
lag ausserhalb des kleinen Hunk-Kontextfensters und war damit fuer den
Judge unsichtbar -- ein Informationsproblem, kein Modell-Faehigkeits-
problem.

Aenderung gegenueber Version 4: TASK_TEMPLATE bekommt einen zusaetzlichen
Platzhalter {full_document_text} -- der VOLLE aktuelle Text derselben
Datei, aus der der Hunk stammt. Klare Rollentrennung bleibt gewahrt:
- Der Hunk bleibt der EINZIGE Bewertungsgegenstand (was wird beurteilt).
- Der Volltext ist REINES Referenzmaterial (womit wird abgeglichen).
Der Judge sucht weiterhin NICHT selbst nach Aenderungen im Volltext --
die Lokalisierung bleibt vollstaendig deterministisch (diff_hunks.py).
Damit bleibt das Kernprinzip aus Abschnitt 3 des Handovers gewahrt.
"""

from __future__ import annotations

from dataclasses import dataclass

ROLE = """Du bist ein erfahrener Technical Writer und Projektmanager. Du bewertest EINE EINZELNE, bereits identifizierte Textänderung in einem Vault-Dokument -- du suchst NICHT selbst nach Änderungen, die Stelle ist bereits bekannt."""

TASK_TEMPLATE = """Folgende Textänderung wurde in einem Vault-Dokument vorgenommen (- = alter Text, + = neuer Text, ohne Präfix = unveränderter Kontext):

Dateiname: {filename}

Änderung:
{hunk_diff_text}

Vollständiger aktueller Text derselben Datei (NUR Referenz, um die Änderung im Gesamtzusammenhang des Dokuments zu prüfen -- suche hier NICHT selbst nach weiteren Änderungen, bewerte ausschließlich die oben gezeigte Änderung):
{full_document_text}

Tatsächlicher, aktueller Gesamtprojektstand (aus frischem Code-/Vault-Scan):
{current_project_concept}

Zusätzlicher Kontext -- Zusammenfassungen anderer Dokumente im selben Projekt:
{recent_worklog_summaries}

Beurteile NUR diese eine Änderung: Ist der NEUE Text (+) durch den Rest des Dokuments, den tatsächlichen Projektstand oder die anderen Dokumente belegt, widerlegt, oder neutral (weder belegt noch widerlegt)?"""

CONSTRAINTS = """Wichtige Einschränkungen:
- Bewerte NUR die gezeigte Änderung. Nutze den vollständigen Dokumenttext und die anderen Kontextquellen NUR als Nachschlage-Referenz, nicht um selbst neue Änderungen darin zu suchen.
- WICHTIG: Wenn der Kontext auf einen Abschnitt wie "Merkposten", "TODO", "Wiedervorlage", "Offene Punkte", "Nächste Schritte" hindeutet, ist es NORMAL und KEIN Widerspruch, dass dort offene Aufgaben stehen -- auch wenn andernorts im Projekt eine übergeordnete Phase als abgeschlossen gilt. Melde das NICHT als is_supported=false.
- WICHTIG: Eine fehlende oder unvollständige "Status:"/"Erreicht:"-Angabe INNERHALB des Abschnitts einer einzelnen Phase/Funktion ist für sich allein KEIN Beleg dafür, dass ein an anderer Stelle (z.B. einer Gesamtstatus-Tabelle) genannter Status FALSCH ist. Fehlende Binnendokumentation ist eine Dokumentationslücke, kein inhaltlicher Widerspruch. Setze in diesem Fall is_supported=true UND ergänze im Feld "reasoning" den Hinweis, dass die Binnendokumentation dieser Phase unvollständig ist -- aber melde es NICHT als is_supported=false, solange keine AKTIV widersprechende Aussage (z.B. eine andere Tabelle mit einem anderen Status) vorliegt.
- WICHTIG: Eine knappe Status-Angabe in einer Gesamtstatus-Tabelle (z.B. "Abgeschlossen (2026-08-24)" ohne Auflistung der einzelnen umgesetzten Punkte) ist KEIN Widerspruch zu einem detaillierteren "Erreicht:"-Block im Phasenabschnitt oder zu einem zusammenfassenden Satz im Dokument -- die Tabelle dient der Übersicht, der "Erreicht:"-Block der Detailnachweise. Setze is_supported=true, wenn der Tabellenstatus mit dem Phasenstatus oder dem zusammenfassenden Satz übereinstimmt, auch wenn die Tabelle weniger Details nennt.
- WICHTIG: Unterschiedliche Datumsangaben (z.B. "Abgeschlossen (2026-08-24)" in der Tabelle vs. "Alle Phasen bis Phase 8 sind abgeschlossen (25.08.2026)" im Fazit) sind KEIN Widerspruch, solange der STATUS-WERT (z.B. "Abgeschlossen") identisch ist. Das Datum kann sich durch spätere Präzisierung ändern, der Status bleibt gleich. Setze in diesem Fall is_supported=true.
- "is_supported=false" bedeutet: der NEUE Text behauptet etwas, das der Rest des Dokuments, der Projektstand oder die anderen Dokumente AKTIV UND KONKRET widerlegen (z.B. eine Phase als "fertig" bezeichnen, die laut einer Tabelle im selben Dokument nachweislich noch offen ist).
- "is_meaningful=false" bedeutet: die Änderung ist trivial (Tippfehler, Formatierung, Synonym) UND steht in keinem inhaltlichen Widerspruch zum Rest des Dokuments. Eine rein formale Änderung (z.B. ein hinzugefügtes Ausrufezeichen) kann trotzdem is_meaningful=true sein, wenn der dadurch veränderte oder betonte Satz inhaltlich im Widerspruch zum restlichen Dokument steht -- bewerte die BEDEUTUNG des resultierenden Satzes, nicht nur die Form der Änderung.

SEVERITY-EINSTUFUNG (bitte genau befolgen, nicht durchgehend LOW wählen):
- HIGH: Die Änderung behauptet einen GESAMTPROJEKTSTATUS (z.B. "alles fertig", "Projekt abgeschlossen"), der durch den Rest des Dokuments, die Worklogs oder andere Dokumente EINDEUTIG UND UMFASSEND widerlegt wird (mehrere offene Phasen).
- MEDIUM: Die Änderung behauptet den Status EINER EINZELNEN, KONKRET BENANNTEN Phase/Funktion, der eindeutig widerlegt wird.
- LOW: Die Änderung ist zwar nicht ganz präzise, aber nur in einer Nuance falsch, oder die Belege sind nur indirekt/schwach.
- Ein Widerspruch, den du selbst in deiner Begründung als "eindeutig belegt" beschreibst, ist NIEMALS LOW -- mindestens MEDIUM.
- Wenn du unsicher bist, OB überhaupt ein Widerspruch besteht, setze is_supported=true. Wenn du dir SICHER bist, DASS ein Widerspruch besteht, aber unsicher über das genaue Ausmaß, wähle MEDIUM als Standardfall, nicht LOW.
- Antworte ausschließlich mit validem JSON, kein Freitext davor oder danach."""

OUTPUT_FORMAT = """Antworte ausschließlich mit einem JSON-Objekt exakt in dieser Struktur:

{
"is_meaningful": true,
"is_supported": false,
"severity": "LOW",
"reasoning": "kurze Begründung, 2-3 Sätze",
"contradiction_summary": "falls is_supported=false: was genau widerspricht sich. Sonst leerer String."
}"""


@dataclass(frozen=True)
class DriftJudgePromptComponents:
    role: str = ROLE
    task_template: str = TASK_TEMPLATE
    constraints: str = CONSTRAINTS
    output_format: str = OUTPUT_FORMAT


def build_drift_judge_prompt(
    filename: str,
    hunk_diff_text: str,
    current_project_concept: str,
    recent_worklog_summaries: str,
    full_document_text: str,
    components: DriftJudgePromptComponents | None = None,
) -> str:
    components = components or DriftJudgePromptComponents()
    task = components.task_template.format(
        filename=filename,
        hunk_diff_text=hunk_diff_text,
        full_document_text=full_document_text or "(kein Volltext verfuegbar)",
        current_project_concept=current_project_concept,
        recent_worklog_summaries=recent_worklog_summaries or "(keine anderen Dokumente vorhanden)",
    )
    return "\n\n".join([components.role, task, components.constraints, components.output_format])
