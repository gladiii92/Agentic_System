# Handover — Agentic_System
## Curator-Agent + Evaluator-Agent → Supervisor → Builder
### Stand: 2026-09-10

Zweck: Dieses Dokument als erste Nachricht im nächsten Chat verwenden. Es ersetzt das bisherige Handover und beschreibt den aktuellen technischen Stand, die real durchgeführten Tests, die offenen Probleme sowie die geplante Zielarchitektur.

---

# 0. Projektkontext

## Hauptprojekt

Repository:

`G:\DAVID\Desktop\GitHub\Agentic_System`

Ziel: Aufbau eines lokal-first, selbst orchestrierten Multi-Agenten-Systems, das sich wie eine kleine Softwareorganisation verhält.

Langfristige Vision:

```text
Nutzer / Founder
      ↓
Supervisor / Control Plane
      ↓
┌──────────────┬──────────────┬──────────────┐
│ Curator      │ Evaluator    │ Builder      │
│ Verwaltung   │ Bewertung    │ Umsetzung    │
└──────────────┴──────────────┴──────────────┘
      ↓
FIS / Projekte / Dateien / Code
```

Der Nutzer ist Ideengeber und Entscheider. Die Agenten übernehmen Analyse, Bewertung und später Umsetzung. Schreibvorgänge bleiben zunächst Human-in-the-Loop.

## Schwesterprojekt

`G:\DAVID\Desktop\GitHub\AI_Project_Reviewer`

Dieses Projekt liefert bereits wichtige Bausteine für Analyse und Concept-Summaries.

## FIS-Testziel

`G:\DAVID\Desktop\GitHub\Founder_Intelligence_System\04_PRODUCT_OS\01_PRODUCTS\AI_PROJECT_REVIEWER\`

Aktuelle Testdatei:

`ROADMAP.md`

---

# 1. Nicht verhandelbare Architekturprinzipien

1. Lokal-first.
   - Primär lokale Modelle über Ollama.
   - Kostenlose Cloud-APIs nur als Eskalationsstufe, wenn lokal nachweislich nicht ausreichend.
   - Keine unnötigen kostenpflichtigen Dienste.

2. Deterministische Teile bleiben deterministisch.
   - Dateisuche
   - Snapshot-Vergleich
   - Chunking
   - Patch-Validierung
   - eindeutige Ersetzung
   - Sicherheitsregeln
   - Budgets / Limits
   - HITL

3. LLMs übernehmen dort, wo semantisches Reasoning benötigt wird.
   - Bewertung
   - Widerspruchserkennung
   - Patch-Vorschlag
   - spätere Planung / Architekturentscheidungen

4. Human-in-the-Loop bei jedem Schreibvorgang.
   - Kein autonomes ungeprüftes Schreiben als aktueller Sicherheitsstandard.

5. Patches müssen minimal und sicher sein:
   - `exact_old_text`
   - `replacement_text`
   - `exact_old_text` muss exakt einmal vorkommen.
   - Patch-Validator entscheidet deterministisch.
   - Fehlgeschlagene Patches werden verworfen.

6. Keine Breaking Changes im Schwesterprojekt `AI_Project_Reviewer`.
   - Änderungen dort ausschließlich additiv.
   - Bestehende Nutzer und Funktionen dürfen nicht verschlechtert werden.
   - JSON-Strukturen / bestehende Consumer nur nach vorheriger Prüfung verändern.

7. Kein Builder-Agent, bevor Curator + Evaluator + Kontrollmechanismen belastbar stehen.

8. Keine unnötige Abhängigkeit von einer Coding-CLI zur Laufzeit.
   - Antigravity / Gemini CLI / Claude Code etc. sind Entwicklungswerkzeuge.
   - Das spätere Agentic_System soll selbstständig über Python, lokale Modellserver und definierte APIs/Adapter funktionieren.

---

# 2. Aktueller Codebestand

Aktuelle relevante Struktur:

```text
agents/
  curator_agent/
    concept_loader.py
    snapshot_store.py
    drift_diff.py
    diff_presenter.py
    run_drift_check.py
    run_full_audit.py

  evaluator_agent/
    evaluator.py
    drift_judge_prompt.py
    full_audit_judge_prompt.py
    patch_writer.py
    patch_writer_prompt.py
    model_clients.py
    rejection_history.py

patching/
  document_chunker.py
  diff_hunks.py
  patch_models.py
  patch_validator.py
  patch_applier.py
```

Weitere relevante Infrastruktur:

- `.env` im Repo-Root
- `.env` ist in `.gitignore`
- `GEMINI_API_KEY`
- `GROQ_API_KEY`
- `python-dotenv`
- lokales Ollama

Aktuell aktive Patch-Writer-Eskalation:

```python
PATCH_WRITER_MODEL_TIERS = ("groq",)
```

---

# 3. Normaler Curator / Drift-Check

Der normale Drift-Check arbeitet weiterhin nach dem Prinzip:

```text
Datei
 ↓
Snapshot / mtime
 ↓
deterministischer Diff
 ↓
Hunks
 ↓
Evaluator / Judge
 ↓
Score
 ↓
bei relevantem Finding:
    Patch Writer
        ↓
    Patch Validator
        ↓
    HITL
```

Der normale Drift-Judge darf weiterhin den vollständigen Dokumentkontext als Referenz verwenden.

Das ist vom Full-Audit-Judge bewusst getrennt.

Testkommando:

```powershell
cd G:\DAVID\Desktop\GitHub\Agentic_System
.\venv\Scripts\Activate
python -m agents.curator_agent.run_drift_check
```

---

# 4. Cloud-Eskalation / Patch Writer

## Ausgangsproblem

Lokale 7B-14B-Modelle konnten die semantische Lokalisierungsaufgabe des Patch Writers wiederholt nicht zuverlässig lösen.

Real getestet wurden mehrere Varianten. Das lokale Modell änderte teilweise die falsche von zwei ähnlich formulierten Stellen.

Der Patch Validator hat diese falschen Vorschläge zuverlässig abgefangen.

## Lösung

Cloud-Eskalation nur für den Patch Writer.

Implementiert:

`agents/evaluator_agent/model_clients.py`

Enthält REST-Wrapper für:

- Gemini
- Groq

Keine zusätzlichen SDKs erforderlich; `requests` reicht.

## Real verifiziert

Groq mit:

`openai/gpt-oss-120b`

hat den problematischen Patch korrekt lokalisiert und einen korrekten minimalen Patch erzeugt.

Gemini wurde ebenfalls getestet, timeoutete aber in 5/5 Versuchen unter den damaligen Bedingungen und ist deshalb aktuell deaktiviert.

Ollama bleibt für den Judge aktiv.

Aktuell:

```text
Judge:
    Ollama / qwen2.5-coder:latest

Patch Writer:
    Groq / openai/gpt-oss-120b

Gemini:
    Code vorhanden, aktuell deaktiviert

OpenRouter:
    noch nicht gebaut
```

---

# 5. Full-Audit-Modus

## Motivation

Der normale Drift-Check erkennt nur neue Änderungen.

Ein Widerspruch, der bereits seit längerer Zeit im Dokument existiert und nicht mehr verändert wurde, erzeugt keinen neuen Diff-Hunk.

Deshalb wurde ein separater Full Audit eingeführt.

Aufruf:

```powershell
python -m agents.curator_agent.run_full_audit ROADMAP.md
```

Der Full Audit ist bewusst nicht Bestandteil jedes normalen Drift-Laufs, weil er für jedes Dokument mehrere Modellaufrufe erzeugen kann.

---

# 6. Full-Audit-Chunking

Datei:

`patching/document_chunker.py`

Aktuelle Strategie:

```text
DEFAULT_CHUNK_LINES = 200
DEFAULT_OVERLAP_LINES = 10
```

Zeilenbasiertes Chunking wurde bewusst gewählt.

Nicht headerbasiert, weil beliebige Dokumente verarbeitet werden sollen und nicht jedes Dokument Markdown-Überschriften besitzt.

Der Overlap reduziert das Risiko, dass ein Satz genau an einer Chunk-Grenze getrennt wird.

---

# 7. Full-Audit-Judge — aktuelle Architektur

Neue Datei:

`agents/evaluator_agent/full_audit_judge_prompt.py`

Der Full-Audit-Judge wurde bewusst vom normalen Drift-Judge getrennt.

Aufgabe:

> Einen gelieferten Dokument-Chunk aktiv auf interne Widersprüche prüfen.

Regeln:

- Nur Aussagen innerhalb des gelieferten Chunks bewerten.
- Zwei konkrete Textstellen müssen den Widerspruch belegen.
- Unterschiedliche Datumsformate sind kein Widerspruch, wenn sie semantisch dasselbe Datum darstellen.
- Synonyme / unterschiedliche Formulierungen sind kein Widerspruch, wenn sie dieselbe Aussage bedeuten.
- Fehlende Informationen sind kein Widerspruch.
- Vermutungen sind kein Widerspruch.
- `is_supported=false` bedeutet einen tatsächlich belegbaren Widerspruch.
- `is_meaningful=true` bei einem echten Widerspruch.
- HIGH für zentrale Gesamtstatus-/Abschlusswidersprüche.
- MEDIUM für einzelne Phasen/Funktionen.
- LOW für kleinere Inkonsistenzen.

Der Judge verwendet aktuell absichtlich nur den Chunk.

---

# 8. Warum der Full-Audit-Judge KEINEN vollständigen Dokumenttext mehr bekommt

Das wurde empirisch untersucht.

Getestete Varianten:

### Variante A
Kleiner relevanter Ausschnitt (~300 Zeichen)

→ echter Widerspruch korrekt erkannt.

### Variante B
Relevanter Chunk (~4.000 Zeichen), ohne Volltext

→ echter Widerspruch korrekt erkannt.

### Variante C
Chunk (~4.000 Zeichen) + vollständiges Dokument (~9.000 Zeichen)

→ echter Widerspruch wurde übersehen und stattdessen wurden irrelevante / halluzinierte Konflikte erzeugt.

Zusätzlich wurden Tests mit:

- `current_project_concept`
- `recent_worklog_summaries`
- `full_document_text`

durchgeführt.

Diese zusätzlichen Kontextquellen verschlechterten die Leistung des lokalen Judges ebenfalls.

## Schlussfolgerung

Das Problem ist nicht primär zu wenig Kontext.

Zu viel redundanter Kontext verschlechtert die lokale Modellleistung.

Deshalb gilt aktuell:

```text
Full-Audit-Judge
    ↓
nur relevanter Chunk
```

Nicht:

```text
Chunk + kompletter Dokumenttext + Summary + Worklogs
```

---

# 9. Wichtigster aktueller Full-Audit-Befund

Der reale Test wurde am 2026-09-10 durchgeführt:

```powershell
python -m agents.curator_agent.run_full_audit ROADMAP.md
```

Ergebnis:

```text
15 Dokument(e) zusammengefasst.
2 Chunk(s) gefunden.
```

## Chunk 1

```text
Zeilen 1-210
```

Judge:

```text
is_meaningful=True
is_supported=False
severity=HIGH
Score: 8.80
approved=True
```

Er erkannte einen realen Widerspruch bei Phase 2.5:

- Status: „Abgeschlossen und real verifiziert“
- gleichzeitig offener Merkposten zur Umstellung von Option A auf Option B

Der Patch Writer schlug vor:

```text
Status: Abgeschlossen und real verifiziert
→
Status: Abgeschlossen
```

Der Patch Validator lehnte dies korrekt ab, weil:

```text
exact_old_text kommt 5x im Dokument vor
```

Das zeigt:

- Judge funktioniert grundsätzlich.
- Patch Writer kann einen Vorschlag erzeugen.
- Validator verhindert eine nicht eindeutige automatische Änderung.

## Chunk 2

```text
Zeilen 191-294
```

Judge:

```text
is_meaningful=True
is_supported=True
severity=LOW
```

Kein Widerspruch erkannt.

---

# 10. Der aktuell entscheidende Full-Audit-Fehler

Der bewusst eingebaute Haupttestfall wurde NICHT erkannt.

Im Dokument existiert ein Widerspruch zwischen:

```text
Phase 3 = Nächster Schritt
weitere Phasen = Offen
```

und einer späteren Aussage sinngemäß:

```text
Alle Phasen bis Phase 8 sind abgeschlossen.
```

Die beiden Aussagen liegen in unterschiedlichen Chunks:

```text
Chunk 1: Zeilen 1-210
Chunk 2: Zeilen 191-294
```

Dadurch kann ein reiner Chunk-Judge den Widerspruch nicht erkennen.

Das ist keine reine Prompt-Schwäche, sondern eine Architekturgrenze.

---

# 11. Konsequenz: Cross-Chunk Audit

Nicht zurück zu:

```text
Chunk + kompletter Dokumenttext → Judge
```

Das wurde getestet und verschlechtert die Ergebnisse.

Stattdessen soll langfristig ein zweistufiger Full Audit entstehen:

```text
                    FULL AUDIT
                        │
            ┌───────────┴───────────┐
            ↓                       ↓
      Local Chunk Audit       Cross-Chunk Audit
            │                       │
      Chunk 1 → Judge               │
      Chunk 2 → Judge               │
      Chunk 3 → Judge               │
                                    ↓
                         kleine relevante Evidence
                                    ↓
                           Cross-Chunk Judge
```

Die Idee:

1. Einzelne Chunks werden lokal geprüft.
2. Aus Chunks werden relevante explizite Aussagen / Statusinformationen extrahiert.
3. Nur diese kleinen Evidence-Blöcke werden miteinander verglichen.
4. Der Cross-Chunk-Judge bekommt nicht das komplette Dokument, sondern gezielt ausgewählte Aussagen.
5. Deterministische Regeln sollen möglichst viel Vorarbeit leisten.

Beispiel:

```text
Evidence A:
Phase 3 — Status: Nächster Schritt

Evidence B:
Alle Phasen bis Phase 8 sind abgeschlossen.
```

→ kleiner, klarer Kontext für den Judge.

Noch NICHT implementieren, bevor das Design sauber abgestimmt wurde.

---

# 12. Weitere Full-Audit-Offenpunkte

## 12.1 Chunking

Noch nicht ausreichend gegen sehr lange Dokumente getestet.

Aktuell:

```text
200 Zeilen
10 Zeilen Overlap
```

Die 296-Zeilen-ROADMAP erzeugte 2 Chunks.

Noch offen:

- Dokumente mit mehreren tausend Zeilen
- API-Call-Kosten
- sinnvolle maximale Chunk-Größe
- eventuell dynamische Chunking-Strategie

## 12.2 Mehrere Findings pro Chunk

Aktuell liefert `HunkJudgment` nur EIN Urteil.

Noch ungeklärt:

```text
Chunk
 ↓
mehrere unabhängige Widersprüche
 ↓
sollen mehrere Findings möglich sein?
```

Eine Umstellung von einem einzelnen `HunkJudgment` auf eine Liste wäre potenziell Breaking Change.

Nicht vorschnell ändern.

## 12.3 Stale Debug-Ausgabe

`run_full_audit.py` gibt aktuell weiterhin aus:

```text
[DEBUG] full_document_text an Judge: ...
```

Der Full-Audit-Judge bekommt diesen Volltext inzwischen NICHT mehr.

Der Volltext wird weiterhin für Patch-Writer-/Patch-Anwendungslogik benötigt.

Die Debug-Ausgabe ist daher irreführend, aber nicht funktional kritisch.

Später bereinigen.

## 12.4 Stale Docstrings / Imports

In `evaluator.py` beschreibt die Docstring von `run_full_audit_judge()` noch teilweise eine ältere Variante mit Volltext-Kontext.

In `run_full_audit.py` existieren noch einige Imports / Beschreibungen aus der älteren Architektur.

Später bereinigen, nicht während einer größeren Funktionsänderung unnötig umbauen.

---

# 13. AI_Project_Reviewer — Concept Summary

Ein wichtiger Befund aus der vorherigen Session bleibt relevant.

`AI_Project_Reviewer` erzeugt pro Dokument eine kurze Zusammenfassung und anschließend eine verdichtete Projektzusammenfassung.

Problem:

Explizite Statusaussagen können bei der Verdichtung verloren gehen.

Beispiel:

Original:

```text
Phase 3, 4 und 5 sind vollständig real abgeschlossen.
```

Summary:

```text
Das Dokument beschreibt die Abschlussarbeit der offenen Realtests aus Phase 3, 4 und 5.
```

Die zweite Aussage beweist nicht, dass die Phasen abgeschlossen sind.

Für Curator/Evaluator ist diese Information aber wichtig.

## Geplante Verbesserung

`concept_summary.py` soll später additiv erweitert werden, sodass explizite Statusinformationen erhalten bleiben.

Nicht die bestehende Zusammenfassungsfunktion ersetzen.

Vor einer Änderung:

1. Vollständigen aktuellen Inhalt von `concept_summary.py` prüfen.
2. Alle Consumer von `concept_text` / `document_summaries` prüfen.
3. Insbesondere `obsidian_export.py` prüfen.
4. JSON-Struktur kompatibel halten.
5. Erst danach minimal additive Änderung durchführen.
6. Cache neu erzeugen.
7. Regressionstest durchführen.

---

# 14. Antigravity / Coding-Agent Status

Antigravity CLI wurde erfolgreich installiert.

Aktuelle CLI:

```text
Antigravity CLI 1.1.28
```

Verfügbare Modelle wurden u.a. beobachtet:

- Gemini 3.8 Flash
- Gemini 3.7 Flash
- Gemini 3.6 Flash
- Gemini 3.1 Pro
- Claude Sonnet 4.6 Thinking
- Claude Opus 4.6 Thinking
- GPT-OSS 120B

Für Architektur-/Repo-Arbeiten wurde Gemini 3.1 Pro als sinnvolle Wahl betrachtet.

## Aktuelles Problem

Das individuelle Antigravity-Wochenkontingent wurde erreicht.

Angezeigt wurde sinngemäß:

```text
Individual quota reached.
Reset in approximately 167 hours.
```

Deshalb sollen aktuell KEINE unnötigen Antigravity-Prompts verschwendet werden.

Lokale Tests über Ollama können unabhängig davon weiterlaufen.

---

# 15. Wichtige Erkenntnis zur Rolle der Coding-CLI

Eine zentrale Architekturfrage wurde am 2026-09-10 erneut gestellt:

Soll Agentic_System überhaupt selbst gebaut werden, oder soll nach dem Quota-Reset einfach Antigravity CLI angewiesen werden, ein System zu bauen, das diese Funktionalität direkt erzeugt?

Antwort:

## Ja, Antigravity kann beim Bauen des Systems helfen.

Aber:

## Antigravity CLI ist NICHT das eigentliche Zielsystem.

Das Ziel ist ein eigenes Runtime-System.

Unterscheidung:

```text
Antigravity / Claude Code / Gemini CLI
        =
Entwicklungswerkzeug
```

gegen:

```text
Agentic_System
        =
eigenständige Runtime / Orchestrierung
```

Das spätere System soll nicht davon abhängig sein, dass eine Coding-CLI geöffnet ist.

Es soll beispielsweise:

```text
lokales Ollama
      ↓
Python-Orchestrierung
      ↓
Curator
      ↓
Evaluator
      ↓
Supervisor
      ↓
Builder
```

verwenden.

Kostenlose Cloud-APIs können über Adapter als Eskalationsstufen hinzukommen.

Ein LLM benötigt natürlich irgendeine Schnittstelle. „Ohne APIs“ ist deshalb technisch nicht das Ziel.

Gemeint ist:

> Keine Abhängigkeit von einer interaktiven Coding-CLI als Runtime.

Die lokale Ollama-HTTP-Schnittstelle ist dafür völlig ausreichend.

---

# 16. Strategische Empfehlung für die weitere Entwicklung

Nicht das Projekt jetzt wegwerfen und komplett neu starten.

Stattdessen:

1. Aktuellen Curator/Evaluator-Stand sichern.
2. Full-Audit-Konzept sauber abschließen.
3. Cross-Chunk-Mechanismus entwickeln.
4. Concept-Summary-Problem additiv lösen.
5. Curator + Evaluator als belastbares MVP abschließen.
6. Danach Supervisor / Control Plane bauen.
7. Erst danach Builder.

Antigravity darf nach dem Quota-Reset sehr wohl als Coding-Agent verwendet werden, um diese Architektur umzusetzen.

Aber es soll den Code bauen, nicht die Architektur ersetzen.

---

# 17. Supervisor / Control Plane — nächste größere Architektur

Nach Curator + Evaluator soll ein Supervisor entstehen.

Empfohlene Struktur:

```text
orchestration/
  supervisor/
    classifier.py
    policy.py
    router.py
    budget.py
    loop_guard.py
    state.py
```

Aufgaben:

- Aufgabe klassifizieren
- Risiko bestimmen
- Komplexität bestimmen
- lokale vs. Cloud-Ausführung bestimmen
- Budgets erzwingen
- maximale Iterationen festlegen
- maximale Tool Calls festlegen
- Zeit-/Tokenlimits überwachen
- No-Progress-Loops erkennen
- Evaluator-Ergebnis auswerten
- `CONTINUE`
- `ESCALATE`
- `STOP`

Wichtig:

Der Supervisor sollte nicht nur ein weiterer „LLM-Agent“ sein.

Er ist primär Control Plane.

Deterministische Sicherheitsregeln haben Vorrang vor einer LLM-Entscheidung.

---

# 18. Zielarchitektur

Langfristig:

```text
USER TASK
   │
   ↓
Deterministic Preflight
   │
   ↓
Supervisor / Classifier
   │
   ├──────────────→ Local simple task
   │
   ├──────────────→ Local agentic task
   │
   ├──────────────→ Free Cloud escalation
   │
   └──────────────→ Human / stronger external agent
                         │
                         ↓
                    WORKER AGENT
                         │
                         ↓
                     EVALUATOR
                         │
                         ↓
                    SUPERVISOR
                    /    |    \
              CONTINUE ESCALATE STOP
                         │
                         ↓
                    HITL / WRITE
```

Später:

```text
Curator
Evaluator
Builder
Marketing-Agent
Research-Agent
Jarvis / Daily Briefing
weitere spezialisierte Agenten
```

---

# 19. Builder-Agent — bewusst später

Der Builder soll später deutlich agentischer arbeiten dürfen als der aktuelle Patch Writer.

Mögliche Fähigkeiten:

- Repository lesen
- Architektur analysieren
- Plan erstellen
- mehrere Dateien ändern
- Tests ausführen
- Fehler analysieren
- iterieren
- Evaluator aufrufen
- Änderungen nach Bewertung verbessern

Aber:

Der Builder darf nicht einfach unkontrolliert Dateien verändern.

Er braucht:

```text
Supervisor
+
Budget
+
Loop Guard
+
Evaluator
+
HITL
```

Die Frage „Builder als freierer Coding-Agent vs. streng deterministischer Patch-Agent“ ist noch offen.

Für den Builder sind stärkere externe Modelle / OpenRouter später eventuell sinnvoll.

---

# 20. LangGraph

LangGraph wurde als mögliches Ziel-Framework betrachtet.

Noch NICHT eingebaut.

Nicht einbauen, solange die tatsächliche Orchestrierungslogik noch nicht klar genug ist.

Erst Verhalten definieren, dann Framework auswählen.

---

# 21. OpenRouter

Noch NICHT implementiert.

Für Curator/Evaluator aktuell kein dringender Bedarf.

Für einen späteren Builder-Agent möglicherweise interessant, weil stärkere Reasoning-/Coding-Modelle verfügbar sein können.

Nicht vorsorglich Komplexität hinzufügen.

---

# 22. Free-Claude-Code / ähnliche Coding-Proxy-Repositories

Das zuvor geprüfte Free-Claude-Code-Repo wurde nicht als geeigneter Ersatz für den aktuellen automatisierten Patch-Writer bewertet.

Grund:

- interaktiver Coding-Agent-Fokus
- zusätzliche lokale Infrastruktur
- mögliche Provider-/ToS-Fragen
- unnötige Komplexität für die aktuelle kleine REST-Aufgabe

Für einen späteren Builder-Agenten kann die Idee erneut betrachtet werden.

---

# 23. Aktueller Testbefehl

```powershell
cd G:\DAVID\Desktop\GitHub\Agentic_System
.\venv\Scripts\Activate
python -m agents.curator_agent.run_full_audit ROADMAP.md
```

Normaler Drift-Check:

```powershell
python -m agents.curator_agent.run_drift_check
```

---

# 24. Aktueller Gesamtstatus

```text
PHASE 0 — Architektur / Planung
    ✅

PHASE 1 — Curator + Evaluator MVP
    🟡 weit fortgeschritten
    ├── Snapshot / Diff              ✅
    ├── Normal Judge                 ✅
    ├── Patch Writer                 ✅
    ├── Patch Validator              ✅
    ├── HITL                         ✅
    ├── Cloud Escalation             ✅
    ├── Full Audit                   🟡
    └── Cross-Chunk Audit            ❌ offen

PHASE 2 — Wiederverwendbare Eskalation / Supervisor
    ❌

PHASE 3 — Builder
    ❌

PHASE 4 — vollständiger Agentenloop
    ❌

PHASE 5 — weitere Agenten / Jarvis / Multi-Projekt
    ❌
```

---

# 25. Unmittelbare nächste Schritte

Reihenfolge:

## Schritt 1 — NICHT sofort programmieren

Cross-Chunk-Audit konzeptionell sauber definieren.

Ziel:

```text
lokale Chunk-Prüfung
+
kleine Evidence-Auswahl
+
Cross-Chunk-Judge
```

Kein kompletter Dokumenttext beim Judge.

## Schritt 2

Minimalen isolierten Cross-Chunk-Test durchführen:

```text
Evidence A:
Phase 3 = Nächster Schritt

Evidence B:
Alle Phasen bis Phase 8 abgeschlossen
```

Der Judge muss daraus einen HIGH-Widerspruch erzeugen.

## Schritt 3

Erst nach erfolgreichem Test Codearchitektur für Cross-Chunk-Audit festlegen.

## Schritt 4

Concept-Summary in `AI_Project_Reviewer` prüfen und anschließend additiv verbessern.

## Schritt 5

Regressionstests:

- echter Widerspruch → erkannt
- Datumsformat-Differenz → kein False Positive
- identische Aussage → kein False Positive
- Cross-Chunk-Widerspruch → erkannt
- falscher Patch → Validator verwirft
- korrekter Patch → Validator akzeptiert
- normaler Drift-Check bleibt unverändert funktionierend

## Schritt 6

Erst wenn diese Tests bestehen:

> Curator + Evaluator MVP als belastbar betrachten.

## Schritt 7

Supervisor / Control Plane beginnen.

---

# 26. Arbeitsweise für nächste Sessions

- Vor großen Codeänderungen interaktiv abstimmen.
- Keine Blind-Implementierung.
- Erst Ziel und Architektur klären.
- Danach konkrete Dateien/Funktionen identifizieren.
- Bei unsicherem Dateistand lieber vollständige Funktion statt Fragment.
- Minimal-invasive Änderungen.
- Keine unnötigen Refactorings.
- Nach jeder relevanten Änderung real testen.
- Keine Aussage „fertig/stabil/production-ready“, solange die definierten Regressionstests nicht bestanden sind.
- Bei Schwesterprojekt `AI_Project_Reviewer`: ausschließlich additive Änderungen.
- Technische Ursachen erklären, nicht nur Fixes nennen.
- Kosten und API-Verbrauch berücksichtigen.
- Lokale Modelle bevorzugen, solange sie die konkrete Aufgabe zuverlässig lösen.
- Cloud-Eskalation gezielt und nachgewiesen einsetzen.

---

# 27. Wichtigste Erkenntnis aus der aktuellen Session

Der Full Audit ist technisch funktionsfähig, aber noch nicht vollständig korrekt.

Die entscheidende Erkenntnis lautet:

> Mehr Kontext ist nicht automatisch besser.

Der vollständige Dokumenttext hat beim lokalen Judge die Qualität verschlechtert.

Die richtige Richtung ist daher nicht „noch mehr Kontext“, sondern:

```text
kleiner relevanter Kontext
        +
gezielte Evidence
        +
hierarchische Prüfung
```

Genau dieses Prinzip soll später auch die gesamte Agentic-System-Architektur prägen:

```text
LLM bekommt nicht alles.
LLM bekommt das Richtige.
Deterministische Systeme kontrollieren das Ergebnis.
```

Das ist die zentrale Leitidee für die nächsten Ausbaustufen.
