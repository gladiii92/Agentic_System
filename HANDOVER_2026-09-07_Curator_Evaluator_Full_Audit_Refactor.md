# Handover — Agentic_System: Curator/Evaluator, echter Full-Audit-Refactor

**Stand:** 2026-09-07, ca. 15:42 CEST  
**Zweck:** Diese Datei als **erste Nachricht im nächsten Chat** hochladen oder ihren Inhalt einfügen. Sie dokumentiert den kompletten technischen Stand, reale Tests, Fehlerbilder, bereits getroffene Entscheidungen und den exakt empfohlenen nächsten Schritt.

---

## 1. Projektkontext

Der Nutzer (David, Lichtenfels/Bayern) entwickelt `Agentic_System` als kleine, selbst orchestrierte Multi-Agenten-Software-Firma. Curator und Evaluator sind die ersten produktiven Agenten:

- **Curator-Agent:** erkennt Dokumentänderungen über Snapshots/mtime und berechnet deterministische Diff-Hunks.
- **Evaluator-Agent / Judge:** bewertet, ob ein geänderter Text zum Projektwissen passt oder einem belegten Kontext widerspricht.
- **Patch Writer:** formuliert bei bestätigtem Widerspruch einen kleinen, deterministisch validierten Patch.
- **Human-in-the-Loop:** jeder Schreibvorgang bleibt zwingend manuell bestätigt.

### Repositories und relevante Pfade

```text
Agentic_System
G:\DAVID\Desktop\GitHub\Agentic_System

AI_Project_Reviewer (Schwesterprojekt; liefert Konzeptzusammenfassungen)
G:\DAVID\Desktop\GitHub\AI_Project_Reviewer

Founder Intelligence System / FIS-Vault
G:\DAVID\Desktop\GitHub\Founder_Intelligence_System

Test-Projekt-Vault-Ordner
G:\DAVID\Desktop\GitHub\Founder_Intelligence_System\04_PRODUCT_OS\01_PRODUCTS\AI_PROJECT_REVIEWER\
```

Aktuelle zentrale Testdateien:

```text
ROADMAP.md
PRODUCT.md
```

---

## 2. Unveränderbare Architekturprinzipien

Diese Regeln sind vom Nutzer ausdrücklich gewünscht und dürfen bei Änderungen nicht verletzt werden:

1. **Lokalisierung, Validierung und Schreiben bleiben getrennt.**
   - Deterministischer Code lokalisiert Änderungen bzw. Dokumentbereiche.
   - LLM bewertet/fasst zusammen/formuliert Vorschläge.
   - `patch_validator.py` validiert Patches deterministisch.
   - `patch_applier.py` wendet ausschließlich validierte Patches deterministisch an.

2. **Human-in-the-Loop bei jedem Schreiben.**
   - Kein automatisches Schreiben in Vault-Dokumente.
   - Es wird immer Unified Diff + Änderungszusammenfassung gezeigt.
   - Erst nach explizitem `ja` wird geschrieben.

3. **Patches bleiben minimal und sicher.**
   - Ein Patch ist immer `exact_old_text -> replacement_text`.
   - `exact_old_text` muss im aktuellen Dokument **wortwörtlich und genau einmal** vorkommen.
   - Kein LLM-generierter Volltext-Ersatz, keine freie unkontrollierte Restrukturierung.

4. **Schwesterprojekt AI_Project_Reviewer nur additiv verbessern.**
   - Keine bestehende Funktionalität oder bereits genutztes Verhalten verschlechtern.
   - JSON-Feldnamen, Cache-Format und bestehende CLI-Workflows nicht breaking ändern.

5. **Kein Overengineering.**
   - Bestehende Datenstrukturen und die aktuelle Projektarchitektur verwenden.
   - Neue Abstraktionen/Flags/Module nur dann, wenn sie technisch wirklich erforderlich sind.

6. **Bei punktuellen Code-Änderungen immer ganze Funktionen ausgeben.**
   - Der Nutzer arbeitet in Windows/PowerShell und ersetzt Funktionen manuell.
   - In einer früheren Session entstand ein `NameError` durch eine unvollständige Teilanleitung.
   - Bei Unsicherheit über den Dateistand: ganze betroffene Funktion ausgeben, nicht nur wenige Zeilen.

---

## 3. Bestehende Architektur und Dateien

### Curator

```text
agents/curator_agent/
  concept_loader.py
  snapshot_store.py
  drift_diff.py
  diff_presenter.py
  run_drift_check.py
  run_full_audit.py
```

### Evaluator

```text
agents/evaluator_agent/
  evaluator.py
  drift_judge_prompt.py
  patch_writer.py
  patch_writer_prompt.py
  model_clients.py
  rejection_history.py
```

### Patching

```text
patching/
  document_chunker.py
  diff_hunks.py
  patch_models.py
  patch_validator.py
  patch_applier.py
```

---

## 4. Bereits erfolgreich umgesetzte Verbesserungen

### 4.1 Judge-Vollkontext-Fix — erfolgreich

**Ursprünglicher Fehler:** Der Judge bewertete einen Hunk ohne die widersprechende Statustabelle im selben Dokument. Deshalb wurde ein klarer Widerspruch als LOW eingestuft bzw. übersehen.

**Erfolgte Änderungen:**

- `drift_judge_prompt.py`: `{full_document_text}` als Referenzkontext ergänzt.
- `evaluator.py::run_drift_judge()`: Parameter `full_document_text` ergänzt.
- Ollama-Call erhält explizit `num_ctx=8192`.
- `run_drift_check.py`: vollständigen aktuellen Dokumenttext an den Judge weiterreichen.
- `_clip_document_text()` begrenzt Referenztext auf `MAX_FULL_DOCUMENT_CHARS = 20_000`.

**Wichtig:** Der Hunk bleibt beim **Drift-Check** der einzige Bewertungsgegenstand; Volltext ist nur Nachschlagekontext.

### 4.2 Generalisierung anderer Dokumentzusammenfassungen — erfolgreich

Der frühere Filter nur auf Dateinamen mit `worklog` wurde ersetzt.

- Neue Logik: `_other_document_summaries()`
- Nimmt Zusammenfassungen aller anderen Projektdokumente aus `current_summary.document_summaries`.
- Kein projektspezifischer Dateiname mehr nötig.

### 4.3 Cloud-Eskalation für Patch Writer — erfolgreich

Lokale Modelle (`qwen2.5`, `qwen2.5-coder`) waren bei der exakten Lokalisierung von Patch-Zielzeilen nicht zuverlässig genug. Mehrere reale Tests trafen falsche ähnliche Zeilen oder lieferten unvalidierbare Patches.

**Lösung:** `agents/evaluator_agent/model_clients.py`

- `call_gemini(...)` (Code vorhanden, aktuell nicht aktiv)
- `call_groq(...)` (aktiv)
- reine REST-Wrapper mit `requests`, kein SDK
- `.env` im Repo-Root, in `.gitignore`
- `GEMINI_API_KEY=...`
- `GROQ_API_KEY=...`
- `python-dotenv`, `load_dotenv()` in `run_drift_check.py` und `run_full_audit.py`

**Aktive Konfiguration:**

```python
PATCH_WRITER_MODEL_TIERS = ("groq",)
```

**Aktives Groq-Modell (damaliger Stand):**

```python
openai/gpt-oss-120b
```

Groq hat reale, korrekte Patches geliefert. Gemini lieferte in mehreren Tests nur Timeouts und ist daher deaktiviert. Ollama bleibt für den Drift-Judge aktiv, nicht für den Patch Writer.

### 4.4 Full-Audit-Modus — technisch vorhanden, aber konzeptionell noch nicht fertig

Datei:

```text
agents/curator_agent/run_full_audit.py
```

Aufruf:

```powershell
cd G:\DAVID\Desktop\GitHub\Agentic_System
.\venv\Scripts\Activate
python -m agents.curator_agent.run_full_audit ROADMAP.md
```

Aktuelles Verhalten:

1. frisch `concept_summary` im Schwesterprojekt erzeugen;
2. Zieldokument mit `patching/document_chunker.py` in Zeilen-Chunks teilen;
3. jeden Chunk an einen Judge geben;
4. bei Widerspruch Patch Writer und Validierung nutzen;
5. Patchvorschau per Human-in-the-Loop anbieten.

Chunking:

```python
DEFAULT_CHUNK_LINES = 200
DEFAULT_OVERLAP_LINES = 10
```

Testdatei `ROADMAP.md`: ungefähr 294 Zeilen, deshalb 2 Chunks:

```text
Chunk 1: Zeilen 1–210
Chunk 2: Zeilen 191–294
```

### 4.5 Full-Audit stale-context-Bug — behoben

Ein erfolgreicher Patch in Chunk 1 konnte Chunk 2 mit dem alten Dokumentstand prüfen. Dadurch wurde dieselbe bereits gelöste Inkonsistenz erneut gemeldet und Patch-Validierung schlug anschließend fehl.

**Fix:** `_handle_chunk_finding()` liest ganz am Anfang jeder Chunk-Prüfung erneut:

```python
current_full_text_for_judge = full_path.read_text(encoding="utf-8")
```

Dadurch arbeitet jeder Chunk mit dem tatsächlichen Dateistand nach möglichen vorherigen bestätigten Patches.

### 4.6 Groq TPM-Rate-Limit — pragmatischer Fix eingebaut

Realer Fehler:

```text
Groq HTTP 429 / tokens per minute (TPM)
Limit 8000, Used ungefähr 4700–5000, Requested ungefähr 4200
```

Ursache: Bei mehreren Chunks kann Judge + Patch Writer des ersten Chunks das Groq-Tokenbudget so belasten, dass der folgende Patch Writer zu früh startet.

**Eingebaute Lösung in `run_full_audit.py`:**

```python
import time
```

und nach `_handle_chunk_finding(...)` in der Chunk-Schleife:

```python
if chunk.chunk_index < len(chunks) - 1:
    print("  (Pause 15s, um Groq-Rate-Limit (TPM) nicht zu ueberschreiten...)")
    time.sleep(15)
```

Dieser Fix funktionierte im nächsten Lauf: kein 429 bei Chunk 2.

### 4.7 Debug-Transparenz — erfolgreich ergänzt

Der Nutzer verlangte ausdrücklich nachvollziehbare Übergaben, damit keine Entscheidungen erraten werden müssen.

In `run_full_audit.py` wurde ergänzt:

```python
print(
    f"    [DEBUG] chunk_text an Judge ({len(chunk_text)} Zeichen): "
    f"{chunk_text[:300]!r}{'...' if len(chunk_text) > 300 else ''}"
)
print(
    f"    [DEBUG] full_document_text an Judge: {len(clipped_full_text)} Zeichen "
    f"(gekuerzt: {len(clipped_full_text) < len(current_full_text_for_judge)})"
)
```

In `_write_patch_with_escalation()` vor `validate_patch(...)`:

```python
print(f"    [DEBUG] exact_old_text (Stufe '{tier}'): {proposed_patch.exact_old_text!r}")
print(f"    [DEBUG] replacement_text (Stufe '{tier}'): {proposed_patch.replacement_text!r}")
print(f"    [DEBUG] change_summary (Stufe '{tier}'): {proposed_patch.change_summary!r}")
```

`!r` ist wichtig, weil dadurch `\n`, doppelte Leerzeichen und sonst unsichtbare Unterschiede sichtbar werden.

---

## 5. Konzeptzusammenfassungen im AI_Project_Reviewer

Datei:

```text
AI_Project_Reviewer/src/ai_project_reviewer/concept_summary.py
```

(Exakter lokaler Pfad je nach Package-Layout prüfen.)

### Funktionsweise

1. `collect_project_vault_documents()` sammelt Markdown-Dateien.
2. `_summarize_single_document()` macht einen Ollama-Call pro Dokument.
3. `_synthesize_concept_summary()` verdichtet alle Einzelzusammenfassungen in 2–4 Sätzen.
4. Ergebnis wird als `ConceptSummaryResult` gecacht (`concept_summary.json`).

### Additive Prompt-Verbesserung bereits umgesetzt

Die ursprüngliche Zusammenfassung fragte nur nach dem Kernzweck. Dadurch gingen in Worklogs explizite Statusaussagen (z.B. „Phase 3, 4 und 5 sind vollständig real abgeschlossen“) in der Verdichtung verloren.

Die Prompt-Templates wurden deshalb additiv erweitert:

- Einzelzusammenfassung: zusätzlich optionaler knapper Statussatz, **nur wenn explizit/eindeutig im Text belegt**.
- Synthese: explizite Status-/Fortschrittsaussagen möglichst präzise übernehmen, **keine Statusbehauptungen erfinden**.

Keine Felder, Funktionssignaturen oder Cache-Strukturen wurden geändert.

### Kompatibilitätsprüfung mit `obsidian_export.py`

`concept_text` wird dort nur als Freitext an die technische Projektbeschreibung für TF-IDF-Ranking angehängt:

```python
return f"{technical_part}Konzept: {concept_text}\n"
```

Es gibt kein Schema-/Parser-Risiko. Eine etwas reichere Zusammenfassung kann die TF-IDF-Gewichtung leicht verändern, aber nicht die bestehende Funktion brechen.

---

## 6. FIS-Standardisierung: bereits abgelegte Dateien

Der Nutzer hat laut letztem Stand die folgenden erzeugten Dateien bereits im FIS abgelegt:

```text
TEMPLATE_ROADMAP.md
TEMPLATE_WORKLOG.md
ROADMAP_v2.md bzw. ROADMAP.md auf Template-Stand migriert
HANDOVER_2026-08-27_FIS_Project_Health_Monitor_Agent.md
```

### Template-Zielbild

#### Roadmap

Jede Phase soll standardisiert enthalten:

```text
## Phase X — Name

Ziel:
...

Umfang:
- ...

Status: Offen | Nächster Schritt | In Arbeit | Abgeschlossen | Abgeschlossen und real verifiziert

Erreicht:
- konkrete, überprüfbare Nachweise
```

#### Worklog

Jeder Worklog soll standardisiert enthalten:

```text
Projekt: ...
Datum: YYYY-MM-DD
Betroffene Phase(n): ...
Status: ACTIVE | DRAFT | DEPRECATED
[[PRODUCT]]: ...

## Ausgangslage
## Durchgeführt
## Ergebnis
Real verifiziert: ja | nein
## Nächste Schritte / Offene Punkte
## Verknüpfte Dateien
```

### Geplantes Folgeprojekt

Der separate Handover `HANDOVER_2026-08-27_FIS_Project_Health_Monitor_Agent.md` beschreibt einen späteren **FIS Project Health Monitor Agent**:

1. deterministischer Coverage-Checker;
2. Freshness-Checker (Worklog/Roadmap/Code/Git);
3. Template-Compliance;
4. bidirektionale Backlinks;
5. späterer LangGraph-Agent mit vorgeschlagenen Aktionen und Human-in-the-Loop.

Dieser Agent ist **nicht** jetzt in Curator/Evaluator hineinzubauen. Curator/Evaluator bleibt klein und sicher. Health Monitor wird später ein eigenständiges Vorhaben.

---

## 7. Wichtige Testbefunde

### 7.1 ROADMAP.md: echter Widerspruch, der gefunden werden MUSS

In der aktuellen `ROADMAP.md` steht in der Gesamtstatus-Tabelle sinngemäß:

```markdown
| Phase | Status |
|---|---|
| 1 — Scanner-Fundament | Abgeschlossen |
| 2 — Context Builder | Abgeschlossen |
| 2.5 — FIS-Sync | Abgeschlossen |
| 3 — Ollama Integration | Nächster Schritt |
| 4 — Finding Store | Offen |
| 5 — Static Analysis | Offen |
| 6 — Prompt Export | Offen |
| 7 — Feedback-Loop | Abgeschlossen |
| 8 — FIS-Integration | Abgeschlossen (2026-08-24) |

Alle Phasen bis Phase 8 sind abgeschlossen (25.08.2026). Alle Phasen gelten als abgeschlossen.
```

**Das ist ein eindeutiger interner Widerspruch:**

- Die Tabelle sagt: Phase 3 = `Nächster Schritt`; Phase 4–6 = `Offen`.
- Der Fazit-Satz sagt: alle Phasen 1–8 seien abgeschlossen.

Der korrekte Full-Audit muss dies finden, auch wenn der Nutzer nur ein einzelnes Satzzeichen irgendwo in der Datei ändert oder gar keine neue Änderung vorliegt.

### 7.2 Was bisher schiefging

Der aktuelle `run_full_audit.py` verwendete anfänglich weiterhin:

```python
run_drift_judge(...)
```

Der Drift-Judge ist fachlich für **einen konkreten Diff-Hunk** gebaut:

```text
„Ist der NEUE Text dieser bereits identifizierten Änderung durch den Rest belegt oder aktiv widerlegt?“
```

Er ist nicht dafür gebaut, ohne Diff aktiv das ganze Dokument nach Widersprüchen abzusuchen.

Deshalb meldete der alte Full-Audit bei vollständigen Chunks oft unsinnige Aussagen wie:

```text
„Die Änderung ist trivial ...“
„Die Änderung ergänzt den Gesamtstatus-Block ...“
```

obwohl im Full-Audit überhaupt keine reale Änderung in diesem Chunk vorlag.

### 7.3 Fehlversuch: Prompt in `hunk_diff_text` hineinschieben

Es wurde ein separates `full_audit_judge_prompt.py` entworfen und versucht, dessen vollständigen Prompt so zu übergeben:

```python
full_audit_prompt = build_full_audit_judge_prompt(...)
judgment = run_drift_judge(
    filename=filename,
    hunk_diff_text=full_audit_prompt,
    current_project_concept=current_project_concept,
    recent_worklog_summaries=other_document_summaries,
    full_document_text=clipped_full_text,
)
```

**Dieser Ansatz ist fachlich und technisch falsch und muss entfernt werden.**

Grund: `run_drift_judge()` baut intern seinen eigenen Drift-Prompt. Dadurch wird der Full-Audit-Prompt nur als „Hunk-Text“ verschachtelt; das Modell erhält widersprüchliche Rollen/Anweisungen und halluziniert dann angebliche Änderungen.

**Wichtig:** Im aktuellen Dateistand könnte dieser Hack noch in `_handle_chunk_finding()` stehen. Er muss durch die saubere Variante aus Abschnitt 8 ersetzt werden.

---

## 8. AKTUELLER NÄCHSTER SCHRITT — saubere Full-Audit-Trennung

### Ziel

`run_full_audit.py` braucht einen **eigenen Judge-Aufruf**, der einen Dokumentabschnitt aktiv auf Konsistenz prüft.

Nicht:

```text
Drift-Check: Ist diese konkrete Änderung korrekt?
```

Sondern:

```text
Full-Audit: Gibt es eine aktive inhaltliche Inkonsistenz
innerhalb dieses Chunks oder zwischen diesem Chunk und dem Volltext?
```

### Saubere Architektur

#### A. Neue Prompt-Datei

Neue Datei:

```text
agents/evaluator_agent/full_audit_judge_prompt.py
```

Sie soll enthalten:

- `ROLE`
- `TASK_TEMPLATE`
- `CONSTRAINTS`
- Severity-Regeln
- `OUTPUT_FORMAT`
- `FullAuditJudgePromptComponents`
- `build_full_audit_judge_prompt(...)`

Der Prompt soll ausdrücklich sagen:

1. Dies ist ein **Full-Audit**, kein Diff-Review.
2. Der gesamte Chunk ist Bewertungsgegenstand.
3. Suche aktiv nach **aktiven, konkreten Widersprüchen**:
   - innerhalb des Chunks;
   - Chunk gegen Volltext;
   - Dokument gegen explizite Aussagen aus anderen Dokumentzusammenfassungen.
4. Fehlende Details/fehlende `Erreicht:`-Blöcke sind **nicht** automatisch ein Widerspruch.
5. Gleicher Status bei unterschiedlichen Datumsformaten ist **nicht** automatisch ein Widerspruch.
6. Unterschiedliche Statuswerte sind ein echter Widerspruch, z.B.:

```text
Tabelle: Phase 3 = Nächster Schritt
Fazit: Alle Phasen bis Phase 8 sind abgeschlossen
```

#### B. Neue Evaluator-Funktion

In:

```text
agents/evaluator_agent/evaluator.py
```

Neue Funktion:

```python
def run_full_audit_judge(
    filename: str,
    document_section_to_evaluate: str,
    current_project_concept: str,
    recent_worklog_summaries: str,
    full_document_text: str,
    model: str = DEFAULT_MODEL,
    num_ctx: int = DEFAULT_NUM_CTX,
) -> HunkJudgment:
```

Anforderung:

- baut über `build_full_audit_judge_prompt(...)` den vollständigen **eigenen** Prompt;
- ruft Ollama **direkt** auf;
- verwendet dieselben robusten Fehlerbehandlungen, JSON-Parsing und `HunkJudgment`-Modell wie `run_drift_judge()`;
- `run_drift_judge()` darf **nicht** verändert/beschädigt werden;
- möglichst gemeinsamen internen Helper extrahieren, wenn das ohne Risiko möglich ist; alternativ den bewährten Parse-/Call-Block sauber duplizieren, um keine riskante Refaktorisierung zu erzwingen.

**Wichtig vor dem Schreiben:** Die aktuelle `evaluator.py` vollständig anfordern/lesen. Die genaue Signatur von `call_ollama()` und der tatsächliche JSON-Response-Typ müssen aus der Datei übernommen werden. In einem früheren Vorschlag wurde unbestätigt `response.parsed_json` angenommen; das darf nicht blind übernommen werden.

#### C. `run_full_audit.py` korrekt anpassen

In den Import:

```python
from agents.evaluator_agent.evaluator import (
    EvaluatorError,
    run_full_audit_judge,
    score_judgment_heuristically,
)
```

`run_drift_judge` soll dort nicht mehr benötigt werden, sofern nur `_handle_chunk_finding()` es verwendete.

In `_handle_chunk_finding()` den gesamten Hack mit:

```python
from agents.evaluator_agent.full_audit_judge_prompt import build_full_audit_judge_prompt
full_audit_prompt = build_full_audit_judge_prompt(...)
judgment = run_drift_judge(... hunk_diff_text=full_audit_prompt ...)
```

vollständig entfernen.

Stattdessen direkt:

```python
judgment = run_full_audit_judge(
    filename=filename,
    document_section_to_evaluate=chunk_text,
    current_project_concept=current_project_concept,
    recent_worklog_summaries=other_document_summaries,
    full_document_text=clipped_full_text,
)
```

Der übrige Ablauf von `_handle_chunk_finding()` (Scoring, Patch Writer, Validator, Diff, Human-in-the-Loop, Rejection History) bleibt **unverändert**.

### D. Sehr wichtiger Folgepunkt: Patch-Writer-Prompt ist noch Drift-orientiert

Nach erfolgreicher Trennung des Full-Audit-Judge muss geprüft werden, ob `patch_writer_prompt.py` eine klare Anweisung für Full-Audit-Befunde bekommt.

Denn der Patch Writer erhält derzeit vermutlich:

```python
hunk_text=chunk_text
contradiction_summary=judgment.contradiction_summary
```

Er muss bei Full-Audit verstehen:

- Es gibt keinen alten/neuen Diff-Hunk als Ausgangspunkt;
- der Chunk enthält den zu prüfenden Dokumentausschnitt;
- der `contradiction_summary` beschreibt die konkret zu korrigierende Inkonsistenz;
- er soll den **kleinsten** eindeutigen `exact_old_text` wählen.

Wahrscheinlich ist eine additive Prompt-Zeile/Parameter `audit_mode` sinnvoll, aber **nicht vorschnell bauen**. Erst den realen Full-Audit-Judge-Lauf testen. Wenn der Judge den gewünschten Widerspruch korrekt liefert, dann den Writer testen und anhand seines Debug-Outputs entscheiden.

---

## 9. Erwarteter Akzeptanztest nach dem Refactor

### Test A: echter ROADMAP-Widerspruch

Datei enthält:

```markdown
| 3 — Ollama Integration | Nächster Schritt |
| 4 — Finding Store | Offen |
| 5 — Static Analysis | Offen |
| 6 — Prompt Export | Offen |

Alle Phasen bis Phase 8 sind abgeschlossen (25.08.2026). Alle Phasen gelten als abgeschlossen.
```

Ausführen:

```powershell
python -m agents.curator_agent.run_full_audit ROADMAP.md
```

**Mindest-Erwartung:**

- mindestens ein Chunk meldet:

```text
is_meaningful=True
is_supported=False
severity=HIGH
```

- Begründung benennt konkret die Tabellenwerte Phase 3–6 und den widersprüchlichen Fazit-Satz.
- `contradiction_summary` ist präzise genug für einen Patch Writer.

Beispiel einer guten Begründung:

```text
Die Gesamtstatus-Tabelle nennt Phase 3 als „Nächster Schritt“ sowie Phase 4, 5 und 6 als „Offen“. Der Satz „Alle Phasen bis Phase 8 sind abgeschlossen“ behauptet dagegen einen Gesamtprojektstatus, der durch mehrere offene Phasen im selben Dokument direkt widerlegt wird.
```

### Test B: Patch Writer

**Akzeptabel** wären mindestens zwei Korrekturstrategien:

1. Den falschen Fazit-Satz minimal korrigieren, z.B.:

```text
Nicht alle Phasen bis Phase 8 sind abgeschlossen (25.08.2026).
```

2. Oder den Satz klarer an die Tabelle anpassen, z.B.:

```text
Abgeschlossen sind Phase 1, 2, 2.5, 7 und 8; Phase 3 ist der nächste Schritt, Phase 4–6 sind offen.
```

Nicht akzeptabel:

- Tabelle ohne eindeutige externe Belege auf „abgeschlossen“ umschreiben;
- Status von Phase 3–6 erfinden;
- großen Dokumentblock ersetzen;
- `exact_old_text` mehrfach vorkommend oder nicht wortwörtlich.

Patch muss durch `validate_patch()` gehen und danach wie immer manuell bestätigt werden.

### Test C: keine False Positives

Nach Korrektur des Fazit-Satzes Full-Audit erneut ausführen.

Erwartung:

```text
Kein Widerspruch in diesem Chunk erkannt.
```

Eine reine Satzzeichenänderung (`!` zu `.`) darf **nicht** zu erfundenen Änderungsbehauptungen oder inhaltlichen Patchvorschlägen führen.

### Test D: Drift-Check nicht regressieren

Nach dem Full-Audit-Refactor:

```powershell
python -m agents.curator_agent.run_drift_check
```

Erwartung:

- verwendet weiter ausschließlich `run_drift_judge()`;
- bewertet tatsächliche Diff-Hunks;
- schreibt wie bisher Snapshot nach Ende;
- funktioniert unabhängig von Full-Audit-Prompt/Funktion.

---

## 10. Nicht erneut falsch machen

1. **Nicht weiter am Drift-Judge-Prompt herumregeln, um Full-Audit zu erzwingen.**
   Der Drift-Judge wurde dadurch bereits überfrachtet und falsche Positive/Negative wurden hin- und hergeschoben.

2. **Keinen Full-Audit-Prompt als `hunk_diff_text` an `run_drift_judge()` übergeben.**
   Das war ein fehlerhafter Hack und führte zu erfundenen „Änderungen“.

3. **Nicht behaupten, der Full-Audit sei produktionsreif/stabil, bevor Test A–D bestanden sind.**
   Der normale Drift-Check ist weiter funktionsfähig; der echte Full-Audit ist aktuell noch im Refactor.

4. **Nicht vorschnell Groq als Judge einsetzen.**
   Das gegenwärtige Kernproblem ist Rollen-/Prompt-/Adapter-Trennung, nicht nachgewiesen die Modellstärke. Groq zusätzlich für Judge würde TPM-Last und Rate-Limit-Probleme erhöhen. Erst saubere Full-Audit-Architektur bauen und mit lokalem Ollama testen.

5. **Nicht „fehlende Dokumentation“ mit „falschem Status“ gleichsetzen.**
   Fehlende Status-/Erreicht-Blöcke sind eine Dokumentationslücke. Ein echter Widerspruch braucht zwei aktiv widersprechende Aussagen.

---

## 11. Aktuelle relevante Datenmodelle

Datei:

```text
patching/patch_models.py
```

```python
@dataclass(frozen=True)
class ProposedPatch:
    filename: str
    exact_old_text: str
    replacement_text: str
    change_summary: str

@dataclass(frozen=True)
class ValidatedPatch:
    filename: str
    exact_old_text: str
    replacement_text: str
    change_summary: str
    occurrence_start_index: int
```

Der Debug-Ausdruck in `_write_patch_with_escalation()` kann sicher diese Attribute nutzen.

---

## 12. Arbeitsstil des Nutzers

- Deutschsprachig, technisch fortgeschritten, Windows + PowerShell.
- Will verständliche Begründungen: **warum** tritt etwas auf, nicht nur welchen Code man kopiert.
- Erwartet robuste Senior-Lösungen, keine Hacks/Rateversuche.
- Arbeitet iterativ und testet direkt lokal.
- Bei Code-Anleitungen: exakte Datei + ganze Funktion bei Funktionsersatz.
- Ist kostenbewusst und lokal-first, akzeptiert aber Groq, wenn reale Tests lokale Modellgrenzen nachweisen.
- Reagiert zurecht empfindlich auf übertriebene Erfolgsmeldungen: erst nach klaren Akzeptanztests „fertig/stabil“ nennen.
- Vor jedem Schreiben in reale Dateien bleibt die manuelle Terminal-Bestätigung maßgeblich.

---

## 13. Empfohlener Einstieg im nächsten Chat

1. Dieses Handover lesen und bestätigen, dass der Full-Audit derzeit noch den Drift-Judge-Hack enthält bzw. enthalten könnte.
2. Den **vollständigen aktuellen Inhalt** dieser zwei Dateien anfordern:

```text
agents/evaluator_agent/evaluator.py
agents/curator_agent/run_full_audit.py
```

Optional zusätzlich, falls Full-Audit-Prompt bereits manuell angelegt wurde:

```text
agents/evaluator_agent/full_audit_judge_prompt.py
```

3. Aktuellen Code exakt prüfen (besonders `run_drift_judge()`, `call_ollama()`-Signatur, JSON-Parsing und vorhandene `HunkJudgment`-Definition).
4. Dann die saubere neue `run_full_audit_judge()`-Funktion passend zum echten Code schreiben.
5. `run_full_audit.py::_handle_chunk_finding()` komplett und korrekt ersetzen.
6. Test A ausführen.
7. Erst nach erfolgreichem Test A entscheiden, ob der Patch Writer einen kleinen Full-Audit-Modus-Hinweis benötigt.

---

## 14. Später, nicht jetzt

- Coverage-Checker aus dem FIS Project Health Monitor Handover.
- Freshness-Checker über Worklog/Roadmap/Code/Git.
- Bidirektionale Obsidian-Backlinks.
- LangGraph-Health-Monitor-Agent.
- OpenRouter als weitere Cloud-Stufe, erst wenn Groq faktisch nicht ausreicht.
- Free-Claude-Code/FCC nur für einen künftig bewusst anders designten Builder-Agenten, nicht für Curator/Evaluator.

---

## 15. Kurzstatus

| Bereich | Status |
|---|---|
| Normaler Drift-Check | Funktional, real getestet |
| Judge mit Volltext im Drift-Check | Funktional |
| Patch Writer mit Groq | Funktional, real getestet |
| Patch-Validierung/HITL | Funktional |
| Debug-Ausgaben | Funktional |
| Groq-Pause zwischen Full-Audit-Chunks | Funktional |
| Konzeptsummary-Status-Ergänzung | Additiv umgesetzt |
| FIS Roadmap-/Worklog-Templates | Abgelegt |
| Full-Audit als echter Konsistenz-Audit | **Noch nicht fertig: separaten Judge-Adapter sauber implementieren** |
