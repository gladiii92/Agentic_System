# Handover — Projekt "Agentic_System", Curator-Agent + Evaluator-Agent
## Cloud-Eskalation, Full-Audit-Feature, offene Summary-Qualitätsfrage

Stand: 2026-08-27, ca. 06:45 CEST
Zweck: Dieses Dokument als ERSTE Nachricht im naechsten Chat einfuegen.
Es dokumentiert den kompletten Stand nach einer intensiven Debug- und
Erweiterungs-Session (2026-08-26 bis 2026-08-27), aufbauend auf
`HANDOVER_2026-08-25_Curator_Evaluator_Stand.md`. Alle Dateiinhalte,
Entscheidungen, Testergebnisse und offenen Punkte sind hier vollstaendig
enthalten, damit ohne erneuten Datei-Upload direkt weitergearbeitet
werden kann.

---

## 0. Projektkontext (Kurzfassung, unveraendert gueltig)

Der Nutzer (David, Lichtenfels/Bayern, DE) betreibt mehrere parallele
Software-/Business-Projekte und baut "Agentic_System" als kleine,
selbst orchestrierte Multi-Agenten-Software-Firma: der Nutzer selbst
als Ideengeber, spezialisierte KI-Agenten als ausfuehrende Kraft.

Repo-Pfad: `G:\DAVID\Desktop\GitHub\Agentic_System`
Schwesterprojekt (liefert Bausteine): `AI_Project_Reviewer`
  Pfad: `G:\DAVID\Desktop\GitHub\AI_Project_Reviewer`
FIS-Obsidian-Vault (Founder Intelligence System):
  Pfad: `G:\DAVID\Desktop\GitHub\Founder_Intelligence_System\04_PRODUCT_OS\01_PRODUCTS\AI_PROJECT_REVIEWER\`
Aktueller Test-Zieldateiname: `ROADMAP.md` in diesem Vault-Ordner.

Grundsatzentscheidungen (unveraendert seit Vortag-Handover, weiterhin gueltig):
- Verwaltungs-Agent (Curator) + Bewertungs-Agent (Evaluator) parallel gebaut.
- Modell-Eskalation: lokal (Ollama) -> kostenlose Cloud-Modelle -> manuell.
  **STATUS-UPDATE dieser Session: Cloud-Eskalation ist jetzt TEILWEISE
  GEBAUT UND REAL VERIFIZIERT** (siehe Abschnitt 3).
- LangGraph als Ziel-Framework, noch NICHT eingebaut.
- Human-in-the-Loop bleibt bei JEDEM Schreibvorgang bestehen — unveraendert
  eingehalten, auch fuer alle neuen Cloud-Eskalationsstufen und den neuen
  Full-Audit-Modus.
- Rollout/Deployment bleibt immer manuell.

**NEUE Grundsatzentscheidung dieser Session (2026-08-27, ganz am Ende):**
Wenn das Schwesterprojekt `AI_Project_Reviewer` angefasst wird (siehe
Abschnitt 7, naechster Schritt), gilt: **NUR additive Verbesserungen,
niemals bestehende Funktionalitaet verschlechtern oder Verhalten
aendern, das andere Teile des Systems bereits nutzen.** Explizite
Nutzer-Vorgabe, siehe Abschnitt 7 fuer den konkreten Anwendungsfall.

---

## 1. Der urspruengliche Bug dieser Session: Severity-Kalibrierung (GELOEST)

### 1.1 Ausgangslage (siehe Vortag-Handover Abschnitt 6, TODO Punkt 1)

Der letzte offene Punkt aus dem Vortag war: Judge stufte einen klar
belegten Widerspruch faelschlich als LOW ein (Score 6.20 < 7.0,
faelschlich verworfen). Testfall: in `ROADMAP.md`, Abschnitt "Gesamtstatus",
steht eine Tabelle mit Phasen-Status (Phase 3-7 als "Nächster
Schritt"/"Offen"), aber direkt darunter der Satz "Alle Phasen sind
abgeschlossen UND das Projekt ist FERTIG!(22.08.2026)" — ein klarer,
in sich widersprüchlicher Fall.

### 1.2 Erster Testlauf (2026-08-26 vormittags) — Diagnose

Judge stufte die Aenderung (Hinzufuegen des `!`-Zeichens) korrekt als
`is_meaningful=True, is_supported=False` ein, ABER `severity=LOW` mit
der Begruendung "trivial, nur ein Ausrufezeichen" — score 6.20,
faelschlich verworfen.

**Ursachendiagnose (durch Code-Analyse, nicht Vermutung):**
`run_drift_check.py` uebergab an den Judge nur:
- `current_project_concept=current_summary.concept_text` — das ist eine
  KI-generierte 2-4-Satz-GESAMTPROJEKT-Zusammenfassung, NICHT der
  Rohtext der Datei selbst.
- `recent_worklog_summaries` — gefiltert NUR auf Dateien mit "worklog"
  im Namen (zu projektspezifisch, siehe Abschnitt 2.2 unten).
- Der Hunk selbst zeigte NUR Zeilen 270-271 (den FERTIG-Satz), NICHT
  die Statustabelle, die weiter oben im selben Dokument steht.

Die Statustabelle, die dem Satz widerspricht, tauchte in KEINEM der drei
Kontextbloecke wortwoertlich auf — der Judge konnte den Widerspruch
schlicht nicht SEHEN, unabhaengig von Modellfaehigkeit.

### 1.3 Fix: Vollkontext fuer den Judge (REAL VERIFIZIERT, funktioniert zuverlaessig)

**Aenderung in drei Dateien:**
1. `drift_judge_prompt.py` (Version 5): neuer Platzhalter
   `{full_document_text}` im `TASK_TEMPLATE`, klar als "NUR Referenz,
   bewerte weiterhin nur den Hunk" markiert.
2. `evaluator.py` (Version 4): `run_drift_judge()` bekommt neuen
   Parameter `full_document_text: str`, UND `num_ctx=8192` wird jetzt
   EXPLIZIT an Ollama gesetzt (siehe 1.4 fuer die Begruendung).
3. `run_drift_check.py`: `new_text` (bereits vorhandene Variable, voller
   aktueller Dateitext) wird jetzt als `full_document_text` durchgereicht.
   Zusaetzlich `_clip_document_text()` als Sicherheitsnetz (Obergrenze
   `MAX_FULL_DOCUMENT_CHARS = 20_000` Zeichen, mit sichtbarem
   Kuerzungshinweis bei Ueberschreitung — kein echtes Chunking, siehe
   Abschnitt 4 fuer den separaten Full-Audit-Chunking-Mechanismus).

### 1.4 Wichtiger Nebenfund: Ollama num_ctx-Falle

Recherche ergab: Ollama laedt Modelle OHNE expliziten `num_ctx`-Parameter
oft mit einem sehr kleinen Default-Kontextfenster (teils nur 2048-4096
Tokens), UNABHAENGIG vom nativen Modell-Limit (`qwen2.5-coder` unterstuetzt
nativ 32K Tokens). Ohne explizite Angabe waere der neu hinzugefuegte
Volltext-Kontext bei laengeren Dokumenten LAUTLOS abgeschnitten worden —
faktisch derselbe Bug wie der urspruengliche, nur eine Ebene tiefer.
**Fix:** `"num_ctx": 8192` explizit in den Ollama-Request-Optionen gesetzt.
8192 Tokens reichen fuer Dokumente bis ca. 25.000-30.000 Zeichen, sicher
fuer die Zielhardware (RTX 2070 Super, 8GB VRAM).

### 1.5 Ergebnis nach dem Fix — REAL VERIFIZIERT

Zweiter Testlauf (gleicher Fall, `!` erneut hinzugefuegt fuer neuen Hunk):
`severity=HIGH`, Score 8.80, `approved=True`, Begruendung praezise
("Phase 3 noch offen laut Rest des Dokuments"). **Kernproblem war
Informationsmangel, nicht Modellfaehigkeit — der Judge-Fix ist
abgeschlossen und stabil, seither in JEDEM weiteren Testlauf
zuverlaessig korrekt.**

### 1.6 Generalisierung des Worklog-Filters (parallel erledigt)

Nutzer-Einwand (berechtigt): `_recent_worklog_summaries()` filterte NUR
Dateien mit "worklog" im Namen — zu spezifisch fuer dieses eine
Testprojekt, widerspricht dem Ziel "beliebige Projekte/Ordnerstrukturen
ohne Sonderwissen ueber Dateinamen". **Fix:** Funktion umbenannt zu
`_other_document_summaries()`, sammelt jetzt Zusammenfassungen ALLER
anderen Dokumente im Projekt (aus `current_summary.document_summaries`),
unabhaengig vom Dateinamen. Kein Namensfilter mehr. Funktioniert seither
generisch fuer beliebige Projektstrukturen.

---

## 2. Der zweite Bug: Patch-Writer trifft wiederholt die FALSCHE Zeile (GELOEST via Cloud-Eskalation)

### 2.1 Symptom (FUENF aufeinanderfolgende Fehlschlaege, alle real getestet)

Nachdem der Judge zuverlaessig funktionierte, produzierte der
Patch-Writer (`qwen2.5:latest`, dann `qwen2.5-coder:latest`, beide
lokal via Ollama) wiederholt FALSCHE Korrekturen:

1. **Versuch 1** (qwen2.5:latest): Hat die Tabellenzeile zu Phase 8
   verstuemmelt (Info geloescht statt korrigiert: `| 8 — FIS-Integration
   | Offen |  |` statt korrektem Status).
2. **Versuch 2** (qwen2.5:latest): Nur ein Trennzeichen `|` am Zeilenende
   entfernt, Tabelle syntaktisch kaputt, Widerspruch NICHT geloest,
   `change_summary` frei erfunden ("Trennzeichen entfernt fuer
   Konsistenz" — voellig falsche Begruendung).
3. **Versuch 3** (qwen2.5-coder:latest, nach Prompt-Praezisierung
   "Standardregel: Hunk-Zeile ist Korrekturziel"): Patch-Validierung
   schlug fehl (`exact_old_text` nicht wortwoertlich im Dokument,
   Laengenverhaeltnis 3.4x ueber Grenze) — vom `patch_validator.py`
   korrekt automatisch abgefangen, NIE angezeigt.
4. **Versuch 4** (qwen2.5-coder:latest, gleicher Prompt): Hat die FALSCHE
   von zwei aehnlichen Zeilen getroffen — Status-Feld bei Zeile 132
   (`Status: Nächster Schritt`, war vorher KORREKT) faelschlich auf
   "Abgeschlossen" geaendert, waehrend die tatsaechlich fehlerhafte
   Tabellenzeile (263-264) unangetastet blieb.
5. **Versuch 5** (identisch): Dasselbe Muster nochmal, mit umgekehrtem
   Zielwert ("Offen" statt "Abgeschlossen") — reproduzierbar, nicht
   zufaellig.

**Wichtige Erkenntnis aus der Fehleranalyse:** Der `TASK_TEMPLATE` in
`patch_writer_prompt.py` hatte urspruenglich KEINE klare Regel, WANN der
Hunk selbst das Korrekturziel ist und wann eine andere Stelle im
Dokument gewaehlt werden soll — das Modell hat sich bei zwei aehnlich
klingenden Zeilen ("Phase 3" + "Nächster Schritt" kommt an ZWEI Stellen
im Dokument vor: Status-Feld UND Tabellenzeile) wiederholt fuer die
FALSCHE Stelle entschieden.

### 2.2 Zwischenversuch: Prompt-Praezisierung (TEILWEISE erfolgreich, aber nicht ausreichend)

`patch_writer_prompt.py` Version 3 fuegte eine explizite STANDARDREGEL
hinzu: "Die zu korrigierende Stelle ist im Regelfall GENAU die im Hunk
gezeigte Zeile selbst — nicht eine andere, thematisch aehnliche Zeile."
Mit Ausnahmefall-Klausel fuer Faelle wie den urspruenglichen FERTIG-Satz
(wo tatsaechlich eine ANDERE Stelle als der Hunk selbst korrigiert
werden musste).

**Ergebnis:** Half NICHT zuverlaessig — Versuch 5 (siehe oben) trat AUCH
mit dieser praezisierten Regel auf. Nutzer-Fazit nach fuenf Fehlschlaegen
mit zwei verschiedenen Ollama-Modellen: "Das Modell gibt einfach immer
eine falsche Ergänzung aus" — empirisch bestaetigt, keine reine
Prompt-Frage mehr, sondern eine Modell-Faehigkeitsgrenze fuer diese
spezifische Lokalisierungsaufgabe bei kleinen, lokal laufenden Modellen
(7B-14B-Klasse).

### 2.3 Loesung: Cloud-Eskalation gebaut und real verifiziert

**Nutzer-Entscheidung:** Kostenlose Cloud-APIs (Google Gemini, Groq) als
Fallback-Stufen NUR fuer den Patch-Writer (nicht fuer den Judge — dort
kein empirisch belegter Bedarf). Ausloeser: `validate_patch().passed=False`
(technischer ODER inhaltlicher Fehlschlag).

**Neues Modul:** `agents/evaluator_agent/model_clients.py` — reine
REST-Wrapper via `requests` (KEIN neues SDK, konsistent mit dem
bestehenden `requests`-Only-Stil des Projekts):
- `call_gemini(prompt, model, timeout_seconds)` — Google AI Studio API.
- `call_groq(prompt, model, timeout_seconds)` — GroqCloud API
  (OpenAI-kompatibles Format).
- Beide lesen den jeweiligen API-Key aus `os.environ` (`GEMINI_API_KEY`,
  `GROQ_API_KEY`), befuellt via `.env`-Datei im Projektroot + `python-dotenv`.

**Aenderung in `patch_writer.py` (Version 3):** `write_patch()` bekommt
neuen Parameter `model_tier: str` (`"ollama"`, `"gemini"`, `"groq"`).
Prompt-Aufbau bleibt fuer alle drei Stufen IDENTISCH — nur der Transport
zum jeweiligen Modell unterscheidet sich.

**Aenderung in `run_drift_check.py` (Version 2026-08-26c/d):**
- `load_dotenv()` wird jetzt einmalig beim Modul-Import aufgerufen.
- Neue Konstante `PATCH_WRITER_MODEL_TIERS` steuert die
  Eskalationsreihenfolge.
- Neue Funktion `_write_patch_with_escalation()`: versucht
  `write_patch()` + `validate_patch()` nacheinander fuer jede Stufe in
  `PATCH_WRITER_MODEL_TIERS`, protokolliert jede Stufe im Terminal.

### 2.4 API-Modellnamen-Probleme (real aufgetreten, geloest)

**Problem 1:** `gemini-2.5-pro` lieferte 404 ("no longer available to
new users"). **Fix:** `DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"`
(aktuell kostenloser Tier, Stand 2026-08-26/27 — **WICHTIG: diese
Modellbezeichnungen aendern sich haeufig, bei erneutem 404-Fehler zuerst
hier nachsehen, bevor Code-Logik infrage gestellt wird**).

**Problem 2:** `llama-3.3-70b-versatile` lieferte 404 bei Groq ("does not
exist or you do not have access"). **Fix:**
`DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"` (aktuell aktives Modell im
Groq-Katalog, Stand 2026-08-26/27).

### 2.5 REAL VERIFIZIERT — Ollama fuer Patch-Writer ausgeschlossen, Cloud funktioniert

**Testlauf nach Modellnamen-Fix:** Ollama wurde als erste Stufe uebersprungen
(nach Nutzer-Entscheidung, siehe 2.2 — "scheißen wir erstmal auf Ollama").
`PATCH_WRITER_MODEL_TIERS` auf `("gemini", "groq")`, spaeter auf
**`("groq",)` alleine** reduziert (siehe 2.6).

Gemini timeoutete zuverlaessig (90s Timeout, FUENF von FUENF Versuchen
gescheitert — vermutlich Rate-Limiting/Priorisierung im kostenlosen Tier).
Groq (`openai/gpt-oss-120b`) lieferte auf Anhieb einen KORREKTEN Patch:
richtige Zielzeile getroffen (Tabellenzeile, nicht das Status-Feld),
korrekter Wert, `change_summary` stimmte mit dem tatsaechlichen Diff
ueberein. **Bestaetigt Nutzer-Vermutung: es war eine Modell-
Faehigkeitsgrenze der lokalen 7B-14B-Modelle, kein reines Kontextproblem
wie beim Judge.**

### 2.6 Aktuelle Konfiguration (Stand Ende dieser Session)

`PATCH_WRITER_MODEL_TIERS = ("groq",)` — NUR Groq, sowohl in
`run_drift_check.py` als auch in `run_full_audit.py`. Gemini und Ollama
sind aus der aktiven Kette entfernt (Code bleibt bestehen, kann jederzeit
durch Aendern dieser einen Konstante wieder aktiviert werden). Grund:
Gemini lieferte 0/5 verwertbare Ergebnisse (nur Timeouts, 90s
Wartezeit pro Versuch, reine Zeitverschwendung), Ollama 0/5 fuer diese
spezifische Aufgabe (siehe 2.1).

---

## 3. Cloud-Provider-Uebersicht (fuer kuenftige Entscheidungen)

| Anbieter | Status | Modell aktuell genutzt | Kostenloses Limit (Stand Recherche 2026-08-26) | Bemerkung |
|---|---|---|---|---|
| Ollama (lokal) | Weiterhin genutzt fuer JUDGE | `qwen2.5-coder:latest` | unbegrenzt, lokal | Zuverlaessig fuer Analyseaufgabe, NICHT fuer Patch-Writer-Formulierung |
| Google Gemini | Code vorhanden, AKTUELL DEAKTIVIERT | `gemini-3-flash-preview` | 5 RPM, ca. 25-100 RPD je Modell/Quelle | 5/5 Timeouts in Tests, unklar ob strukturelles Problem oder Tageszeit-Zufall |
| Groq | AKTIV, funktioniert zuverlaessig | `openai/gpt-oss-120b` | 30 RPM, bis 14.400 RPD je Modell | Einziges bisher erfolgreich real verifiziertes Cloud-Modell fuer Patch-Writer |
| OpenRouter | NICHT gebaut, vorgemerkt | — | 50 Anfragen/Tag ohne Zahlung, 20 RPM; 1.000/Tag nach einmaliger 10$-Aufladung | Siehe Abschnitt 6.3 fuer Begruendung, warum noch nicht gebaut |

**API-Keys liegen in `.env` im Projektroot** (`GEMINI_API_KEY`,
`GROQ_API_KEY`), `.env` ist in `.gitignore` eingetragen (vom Nutzer
bestaetigt). `python-dotenv` wird verwendet, `load_dotenv()` wird in
`run_drift_check.py` UND `run_full_audit.py` beim Modul-Import
aufgerufen (jeweils eigener Aufruf, da beide Module unabhaengig
gestartet werden koennen).

---

## 4. Neues Feature: "Full Audit"-Modus (GEBAUT, TEILWEISE REAL VERIFIZIERT)

### 4.1 Warum dieses Feature entstanden ist

Nutzer-Beobachtung: `run_drift_check.py` erkennt NUR neue Aenderungen
zwischen zwei Snapshots (deterministischer mtime-Diff + Hunk-Diff) —
bereits LAENGER BESTEHENDE Widersprueche im Dokument (die sich seit dem
letzten Snapshot nicht mehr veraendert haben) werden NIE gefunden. Das
ist bewusstes Architekturprinzip aus dem Vortag-Handover (Drift-
Erkennung, nicht Vollstaendigkeitspruefung), aber der Nutzer wollte
zusaetzlich einen Weg, um bestehende Inkonsistenzen zu finden.

### 4.2 Architekturentscheidung: Zeilen-basiertes Chunking, NICHT Header-basiert

Nutzer-Einwand (berechtigt): "Nicht in jedem Dokument gibt es
##-Header." Chunking nach Markdown-Ueberschriften wuerde nur fuer
Dokumente mit konsistenter Ueberschriftenstruktur funktionieren, nicht
generisch fuer beliebige Textdateien.

**Geloest mit:** `patching/document_chunker.py` (NEUES Modul) — teilt
Dokumente in Zeilenbloecke (`DEFAULT_CHUNK_LINES = 200`) mit
Ueberlappung (`DEFAULT_OVERLAP_LINES = 10`), damit ein Satz, der genau
an einer Chunk-Grenze auseinandergerissen wird, trotzdem in mindestens
einem Chunk vollstaendig sichtbar bleibt. ZUSAETZLICH bekommt jeder
Chunk das KOMPLETTE Dokument als Referenzkontext mitgeliefert (gleicher
Mechanismus wie beim Judge-Fix, Abschnitt 1.3) — das federt
Grenzfaelle ueber Chunk-Grenzen hinweg zusaetzlich ab.

### 4.3 Neues Kommando: `run_full_audit.py`

**Aufruf:** `python -m agents.curator_agent.run_full_audit <dateiname>`
Beispiel: `python -m agents.curator_agent.run_full_audit ROADMAP.md`

**Bewusst SEPARAT von `run_drift_check.py`, NICHT automatisch bei jedem
normalen Lauf mitgestartet.** Grund: verursacht MEHRERE API-Calls PRO
CHUNK (Judge + ggf. Patch-Writer-Eskalation) — bei einem laengeren
Dokument mit vielen Chunks waere das ein erheblicher, ungewollter
Mehrverbrauch bei jedem normalen Drift-Check-Lauf.

**Wiederverwendet die EXAKT gleiche, bereits real verifizierte
Judge-/Patch-Writer-/Validierungs-/Human-in-the-Loop-Logik wie
`run_drift_check.py`** — keine neue Prompt-Logik, keine neue
Judge-Logik, nur ein anderer Weg, WAS als "zu pruefender Ausschnitt" an
den Judge gegeben wird (ein kompletter Chunk statt eines echten
Diff-Hunks).

### 4.4 Bug waehrend der Entwicklung (gefunden UND gefixt, real verifiziert)

**Symptom:** Beim ersten Testlauf mit zwei Chunks wurde nach dem
erfolgreichen Schreiben eines Patches in Chunk 1 in Chunk 2 GENAU
DERSELBE bereits behobene Widerspruch nochmal gemeldet — Patch-Writer
versuchte, eine Zeile zu zitieren, die nach dem ersten Patch NICHT MEHR
existierte (`exact_old_text kommt NICHT WORTWOERTLICH im aktuellen
Dokument vor`).

**Ursache:** `full_document_text`/`clipped_full_text` wurde in der
urspruenglichen Implementierung NUR EINMAL am Anfang von `run()`
berechnet, nie zwischen den Chunks aktualisiert — Chunk 2 wurde also mit
einem BEREITS VERALTETEN Dokumentstand bewertet.

**Fix:** `_handle_chunk_finding()` liest jetzt `full_path.read_text()`
GANZ AM ANFANG der Funktion, VOR JEDEM Chunk erneut, statt einmalig
vorher. Kein zusaetzlicher API-Call dadurch, nur eine zusaetzliche,
praktisch kostenlose Datei-Leseoperation. **Nebeneffekt (vom Nutzer
gewuenscht):** verhindert dadurch AUCH, dass unnoetige, zum Scheitern
verurteilte API-Calls bei bereits behobenen Widerspruechen ueberhaupt
erst versucht werden — spart Tokens/Zeit.

**WICHTIG fuer den naechsten Chat:** Dieser Fix wurde per einzelner
Funktions-Ersetzung eingespielt (nicht die ganze Datei neu ausgegeben) —
sollte beim naechsten Testlauf noch einmal explizit bestaetigt werden,
dass er tatsaechlich korrekt im Code angekommen ist (Nutzer hatte
zwischenzeitlich einen `NameError` durch eine unvollstaendige
Zwischenkorrektur, wurde behoben, aber kein erneuter Full-Audit-Lauf
NACH dem finalen Fix wurde in dieser Session mehr durchgefuehrt).

### 4.5 REAL VERIFIZIERT (mit dem Bug aus 4.4 in einem Lauf, VOR dem finalen Fix)

Test 1: Fand den bereits laenger bestehenden Phase-8-Widerspruch
("Offen" in der Tabelle vs. "wurde am 2026-08-24 abgeschlossen" im
Kommentar derselben Zeile) — korrekt erkannt, korrekt via Groq
gepatcht, vom Nutzer bestaetigt und geschrieben.

Test 2 (nach Einfuegen des FERTIG-Satzes durch den Nutzer): Fand den
FERTIG-Satz-Widerspruch, korrigierte ihn KORREKT (nicht die Tabelle
verfaelscht, sondern den Satz selbst praezisiert: "Alle Phasen bis
Phase 7 sind abgeschlossen; Phase 8 wurde am 2026-08-24 abgeschlossen,
das Projekt ist damit fertig (nach 24.08.2026)") — inhaltlich korrekte,
nicht-halluzinierte Loesung. Chunk 2 fand danach einen FOLGE-Widerspruch
(Phase 7 jetzt inkonsistent) und korrigierte auch diesen korrekt.

**Offene Frage, die der Nutzer aufwarf:** Warum wurden Phasen 3-6 NICHT
ebenfalls als "abgeschlossen" markiert, obwohl der FERTIG-Satz das
suggerierte? **Antwort/Klaerung (in dieser Session gegeben, siehe
Abschnitt 5 fuer die volle Herleitung):** Das ist KEIN Fehler, sondern
korrektes Verhalten — Phasen 3-6 sind laut den vorhandenen
Dokumentinhalten (Status-Feldern, Worklog-Zusammenfassungen) tatsaechlich
noch nicht als abgeschlossen belegt. Das System erfindet keine Fakten,
die nicht im verfuegbaren Kontext stehen.

---

## 5. Detaillierte Diagnose: Warum Phasen 3-6 nicht als "fertig" erkannt wurden — UND der daraus entstandene naechste Schritt

### 5.1 Herkunft der `document_summaries`/`concept_text` — geklaert

Nutzer fragte: "Er übergibt doch 15 Dateien und fasst diese kurz
zusammen oder nicht?" — JA, bestaetigt durch Ansicht der echten
`data/curator_snapshots/AI_Project_Reviewer/latest.json`:

- `concept_loader.refresh_and_load()` ruft per Subprocess
  `ai-review build-concept-summary <projekt-pfad> --yes` im
  Schwesterprojekt `AI_Project_Reviewer` auf.
- Dort erzeugt `concept_summary.py` (Modul in `AI_Project_Reviewer`,
  laut dessen eigenem Handover vom 2026-08-22 gebaut) pro Dokument im
  Zielordner GENAU EINEN Ollama-Call fuer eine 1-2-Satz-Zusammenfassung
  (`_summarize_single_document()`), dann EINEN finalen Ollama-Call, der
  ALLE Einzelzusammenfassungen zu 2-4 Saetzen verdichtet
  (`_synthesize_concept_summary()` -> `concept_text`).
- Bei diesem Testprojekt sind das ALLE 15 Dateien im FIS-Vault-Ordner
  `AI_PROJECT_REVIEWER` (PRODUCT.md, STRATEGY.md, FEATURES.md,
  METRICS.md, ROADMAP.md, mehrere Worklog_*.md, ein HANDOVER-Dokument).

**WICHTIGER FUND (Verwechslung in dieser Session aufgeklaert):**
`reviewer_prompt.py` (das dem Nutzer zunaechst als vermeintlicher
Zusammenfassungs-Prompt vorgelegt wurde) ist NICHT fuer
`document_summaries`/`concept_text` verantwortlich — das ist der
Prompt fuer Phase 3 (Ollama Code-Review, erzeugt "Findings" wie
Architekturprobleme/Anti-Patterns/fehlende Tests, voellig andere
Aufgabe). Der TATSAECHLICH verantwortliche Code
(`concept_summary.py::_summarize_single_document()` und
`_synthesize_concept_summary()`) wurde in dieser Session NOCH NICHT im
Volltext gezeigt/gelesen — nur seine Existenz und grobe Funktionsweise
aus dem `AI_Project_Reviewer`-eigenen Handover-Dokument
(`HANDOVER_2026-08-22_Obsidian_Sync_Abschluss.md`, das selbst eines der
15 zusammengefassten Dokumente ist) erschlossen.

### 5.2 Warum die Zusammenfassungen den echten Status nicht klar genug transportieren

Beispiel aus der echten `latest.json` (`Worklog_2026-08-19.md`-Summary):
*"Das Dokument beschreibt die Abschlussarbeit aller offenen
Realtest-Punkte aus Phase 3, 4 und 5 eines AI-Projekts..."*

Das Worklog-Dokument SELBST sagt im Volltext eindeutig: *"Alle vier aus
Worklog_2026-08-10.md offenen Punkte sind abgeschlossen und real... 
verifiziert — Phase 3, 4 und 5 sind damit nicht mehr nur strukturell,
sondern vollständig real abgeschlossen."* — aber die knappe
Ollama-Zusammenfassung dieses Worklogs verliert diese explizite,
eindeutige Status-Aussage und formuliert sie vager ("beschreibt die
Abschlussarbeit..." statt "Phase 3, 4, 5 SIND JETZT FERTIG").

**Kernproblem:** Der Zusammenfassungs-Prompt in `concept_summary.py`
fragt (vermutlich, noch nicht im Code verifiziert) nach dem "Kernzweck"
eines Dokuments, nicht explizit nach dessen STATUS-Aussagen. Dadurch
gehen fuer unseren Judge/Patch-Writer entscheidende
Fertigstellungs-Informationen in der Verdichtung verloren.

### 5.3 Nutzer-Entscheidung zum Vorgehen (WICHTIG fuer naechsten Schritt)

Nutzer hat EXPLIZIT zugestimmt, `concept_summary.py` im Schwesterprojekt
`AI_Project_Reviewer` anzufassen, ABER mit einer klaren, nicht
verhandelbaren Einschraenkung:

> "Nur sollte es halt NUR besser werden dürfen und nicht schlechter....
> Wenn wir das so machen, ist es kein Problem das Projekt anzufassen."

**Bedeutung fuer die Umsetzung im naechsten Chat:** Jede Aenderung am
Zusammenfassungs-Prompt (oder an umgebendem Code in
`AI_Project_Reviewer`) MUSS strikt additiv/verbessernd sein — bestehende
Funktionalitaet, die andere Teile von `AI_Project_Reviewer` ODER von
`Agentic_System` bereits nutzen, darf NICHT veraendert oder verschlechtert
werden. Konkret zu pruefen, BEVOR Code geschrieben wird:
- Wird `concept_text`/`document_summaries` von noch etwas ANDEREM in
  `AI_Project_Reviewer` genutzt (z.B. dem `obsidian_export.py`-Sync-
  Mechanismus aus dessen eigenem Handover, der `concept_text` fuer die
  TF-IDF-Kandidatenanreicherung nutzt, siehe Abschnitt 2.3 dort)? Falls
  ja: eine Verbesserung, die dort zu LAENGEREN/anders strukturierten
  Zusammenfassungen fuehrt, koennte DIESEN anderen Anwendungsfall
  beeinflussen — VOR der Aenderung abklaeren, ob das unproblematisch ist
  oder eine Ruecksprache/Anpassung an zwei Stellen braucht.
- Bestehende gespeicherte `concept_summary.json`-Caches (JSON-Format,
  Feldnamen) duerfen durch die Aenderung nicht invalidiert werden, es sei
  denn, das ist gewollt und wird explizit mit dem Nutzer abgestimmt.

---

## 6. Vorgemerkte, NICHT umgesetzte Themen fuer spaeter

### 6.1 "Free Claude Code" Repo (github.com/alishahryar1/free-claude-code) — GEPRUEFT, AKTUELL NICHT GEEIGNET, aber fuer Builder-Agent vorgemerkt

Nutzer fand dieses Repo und schlug vor, es als Groq-Fallback-Ersatz
einzubauen. **Ergebnis der Pruefung:** FCC ist ein lokaler Proxy-Server,
der die Anthropic/OpenAI-API fuer INTERAKTIVE Coding-Agenten (Claude
Code, Codex, Cline) simuliert — gedacht fuer menschengesteuerte
Terminal-/IDE-Sessions, NICHT fuer programmatische, unbeaufsichtigte
REST-Calls wie unser aktuelles `patch_writer.py`/`evaluator.py`.

**Warum aktuell (Curator/Evaluator) NICHT geeignet:**
1. Zusaetzliche, fuer unseren Fall unnoetige lokale Server-Infrastruktur.
2. Manche Provider (Kimi Code, QwenCloud/Z.ai Coding Plans) sind laut
   Repo-Beschreibung explizit "for local, personal, INTERACTIVE
   coding-agent use" lizenziert — unser automatisierter Batch-Prozess
   ist NICHT interaktiv, potenzielle ToS-Frage.
3. Wuerde unser bestehendes, bereits funktionierendes,
   direktes-REST-Call-Setup unnoetig komplizieren.

**Warum fuer den KUENFTIGEN Builder-Agenten INTERESSANT (Nutzer-Idee,
explizit vorgemerkt):** Falls der Builder-Agent als autonomer, agentischer
Coding-Assistent (mit Datei-Zugriff, Tool-Calls, mehrstufigem Planen)
konzipiert wird — nicht nach dem strikten "deterministisch lokalisieren
-> LLM bewertet nur kleinen Ausschnitt -> deterministisch validieren"-
Muster von Curator/Evaluator — waere FCC ein Weg zu einem kostenlosen,
maechtigeren Agenten-Zugriff. **UNGEKLAERT:** Diese Grundsatzfrage
(Builder-Agent nach Curator/Evaluator-Muster ODER als freierer,
agentischer Assistent) ist NOCH NICHT entschieden — muss vor jedem FCC-
Einsatz erst geklaert werden, da beide Wege sehr unterschiedliche
Validierungs-/Sicherheitsanforderungen haben. **Explizit vom Nutzer
gewuenscht: in diesem Handover vormerken fuer spaeter, JETZT NICHT
umsetzen.**

### 6.2 OpenRouter als dritte Cloud-Eskalationsstufe

Bereits vor der FCC-Diskussion erwogen, dann bewusst zurueckgestellt
(siehe Abschnitt 3 fuer Limit-Details: 50 Anfragen/Tag ohne Zahlung, 20
RPM). Nutzer-Begruendung fuer Zurueckstellung: "Erst Evidenz sammeln,
dann gezielt nachbauen, statt vorsorglich Komplexitaet aufzutuermen" —
Groq funktioniert aktuell zuverlaessig, kein akuter Bedarf.

**ABER:** Nutzer merkte an, dass OpenRouter fuer den KUENFTIGEN
Builder-Agenten relevant werden koennte, weil dort staerkere
Reasoning-Modelle (DeepSeek R1, Qwen3 Coder 480B) kostenlos verfuegbar
sind — dort waere ein staerkeres Reasoning-Modell fuer komplexere
Code-Generierungsaufgaben eher noetig als bei der aktuellen, kleineren
Patch-Writer-Aufgabe. Explizit als moeglicher naechster Schritt fuer die
Builder-Agent-Phase vorgemerkt, NICHT fuer Curator/Evaluator.

### 6.3 Full-Audit — Chunking-Parameter noch nicht optimiert/angepasst

`DEFAULT_CHUNK_LINES = 200`, `DEFAULT_OVERLAP_LINES = 10` sind aktuell
FESTE Konstanten in `document_chunker.py`, noch nicht gegen
unterschiedlich lange/strukturierte Dokumente getestet. Bei sehr langen
Dokumenten (mehrere tausend Zeilen) wuerde das viele Chunks und
entsprechend viele API-Calls erzeugen — noch nicht real getestet, nur
mit der 296-Zeilen-ROADMAP.md (ergab genau 2 Chunks).

### 6.4 Full-Audit — Judge meldet pro Chunk offenbar nur EINEN Fund

Beobachtung aus Test 1 (Abschnitt 4.5): Judge meldete im ersten Chunk
NUR den Phase-8-Widerspruch, nicht gleichzeitig auch den (zu diesem
Zeitpunkt noch nicht eingefuegten) FERTIG-Satz. Unklar, ob der aktuelle
`HunkJudgment`-Datentyp (liefert EIN Urteil, nicht eine Liste) das
grundsaetzlich verhindert, mehrere gleichzeitige Widersprueche in
einem Chunk zu melden. **Nicht weiter untersucht in dieser Session** —
falls relevant, muesste `HunkJudgment` zu einer Liste von Judgments
pro Chunk erweitert werden (Breaking Change fuer bestehende
Aufrufer, sorgfaeltig pruefen).

---

## 7. NAECHSTER SCHRITT (konkret, fuer den Beginn des naechsten Chats)

**Ziel:** `concept_summary.py` in `AI_Project_Reviewer` so verbessern,
dass die pro-Dokument-Zusammenfassungen (`document_summaries`) explizite
Status-/Fortschritts-Aussagen (welche Phase ist laut diesem Dokument
abgeschlossen/offen) NICHT mehr verlieren — damit Judge und Patch-Writer
in `Agentic_System` kuenftig zuverlaessiger erkennen koennen, welche
Phasen eines Projekts laut den vorhandenen Dokumenten tatsaechlich
fertig sind, ohne Fakten zu erfinden.

**Nicht verhandelbare Einschraenkung (siehe Abschnitt 5.3):** NUR additive
Verbesserung, keine Verschlechterung/Aenderung bestehenden Verhaltens,
das andere Teile des Systems (`obsidian_export.py`-Sync o.ae.) bereits
nutzen.

**Konkrete naechste Schritte, in dieser Reihenfolge:**

1. **Datei anfordern:** vollstaendiger Inhalt von `concept_summary.py`
   aus `AI_Project_Reviewer` (Pfad vermutlich
   `src/ai_project_reviewer/concept_summary.py` oder aehnlich — exakter
   Pfad noch nicht bestaetigt, im naechsten Chat vom Nutzer erfragen).
   Insbesondere die Prompt-Formulierung innerhalb von
   `_summarize_single_document()` und `_synthesize_concept_summary()`.
2. **Pruefen, ob/wo `concept_text`/`document_summaries` noch anderswo
   in `AI_Project_Reviewer` verwendet werden** (siehe Abschnitt 5.3,
   `obsidian_export.py` als bekannter Kandidat aus dessen eigenem
   Handover-Dokument) — BEVOR der Prompt geaendert wird.
3. **Vorschlag fuer eine praezisierte Zusammenfassungs-Anweisung**
   entwerfen, die explizit nach Status-Aussagen (Phase X ist
   abgeschlossen/offen, laut diesem Dokument) fragt, OHNE die
   bestehende "1-2 Satz Kernzweck"-Anforderung zu ersetzen — additiv
   ergaenzen, nicht ersetzen (z.B. als zusaetzlicher Hinweisblock im
   Prompt, nicht als Ersatz der bestehenden TASK_TEMPLATE-Struktur, falls
   diese der gleichen Architektur wie `reviewer_prompt.py` folgt —
   vier separate Bausteine role/task/constraints/output_format, siehe
   Abschnitt 5.1 fuer den Hinweis auf dieses Architekturmuster im
   Schwesterprojekt).
4. **Nach der Aenderung:** `latest.json`/`concept_summary.json`-Cache
   fuer das Testprojekt einmal frisch neu generieren lassen (`ai-review
   build-concept-summary <projekt-pfad> --yes`), dann `run_full_audit.py`
   erneut gegen `ROADMAP.md` laufen lassen und pruefen, ob Phasen 3-6
   jetzt korrekt erkannt werden (falls sie laut den echten,
   verbesserten Zusammenfassungen tatsaechlich als abgeschlossen belegt
   sind — WICHTIG: nur wenn das WIRKLICH so im Originaltext steht, sonst
   waere eine "Korrektur" selbst wieder eine Fehlinformation).
5. Danach: bewerten, ob der offene Full-Audit-Bugfix (Abschnitt 4.4)
   im naechsten Testlauf tatsaechlich vollstaendig korrekt eingespielt
   wurde (noch nicht erneut real getestet nach dem letzten Patch).

**Sekundaer, falls Zeit bleibt (nicht prioritaer als Schritt 1-5 oben):**
- Full-Audit-Modus einmal gegen ein LAENGERES Dokument testen (mehr als
  2 Chunks), um das Chunking-Verhalten realistischer zu pruefen
  (Abschnitt 6.3).
- Pruefen, ob Gemini (`gemini-3-flash-preview`) bei anderer Tageszeit/
  geringerer Last zuverlaessiger antwortet, oder ob das strukturell
  ein dauerhaftes Problem ist — aktuell nur 5 von 5 Versuchen zur
  selben Sitzung getestet, keine Langzeit-Beobachtung.

---

## 8. Vollstaendiger Datei-Status (Stand Ende dieser Session)

### Neue Dateien (2026-08-26/27):
- `agents/evaluator_agent/model_clients.py` — Gemini/Groq REST-Clients.
- `patching/document_chunker.py` — Zeilen-basiertes Chunking fuer Full Audit.
- `agents/curator_agent/run_full_audit.py` — separates Full-Audit-Kommando.

### Geaenderte Dateien (mehrfach ueberarbeitet, FINALER Stand ist massgeblich):
- `agents/evaluator_agent/drift_judge_prompt.py` — Version 5,
  Vollkontext-Ergaenzung (`full_document_text`-Platzhalter).
- `agents/evaluator_agent/evaluator.py` — Version 4, `full_document_text`-
  Parameter + explizites `num_ctx=8192`.
- `agents/evaluator_agent/patch_writer_prompt.py` — Version 3,
  Vollkontext + "Standardregel Hunk-Zeile ist Korrekturziel" (half nur
  TEILWEISE, siehe Abschnitt 2.2 — bleibt trotzdem als sinnvolle
  Praezisierung bestehen, auch wenn Cloud-Eskalation das eigentliche
  Loesungsmittel war).
- `agents/evaluator_agent/patch_writer.py` — Version 3, `model_tier`-
  Parameter fuer Ollama/Gemini/Groq-Auswahl.
- `agents/curator_agent/run_drift_check.py` — Version 2026-08-26d,
  Cloud-Eskalation + generalisierter `_other_document_summaries()` +
  `load_dotenv()`. `PATCH_WRITER_MODEL_TIERS = ("groq",)`.

### Unveraendert seit Vortag-Handover (2026-08-25):
- `agents/curator_agent/concept_loader.py`
- `agents/curator_agent/snapshot_store.py`
- `agents/curator_agent/drift_diff.py`
- `agents/curator_agent/diff_presenter.py`
- `patching/diff_hunks.py`
- `patching/patch_models.py`
- `patching/patch_validator.py`
- `patching/patch_applier.py`
- `agents/evaluator_agent/rejection_history.py`
- `config.py` (weiterhin kaum genutzt, siehe Vortag-Handover Abschnitt 6, TODO Punkt 8 — unveraendert offen)

### `.env` (NEU, nicht im Repo, in `.gitignore`):
```
GEMINI_API_KEY=<vom Nutzer eingetragen>
GROQ_API_KEY=<vom Nutzer eingetragen>
```

### `requirements.txt` — pruefen, ob `python-dotenv` tatsaechlich installiert ist
Laut Vortag-Handover bereits in `requirements.txt` gelistet, aber laut
Code-Analyse dieser Session NIE tatsaechlich `import`iert/aufgerufen
gewesen, bis diese Session `load_dotenv()` erstmals einbaute. Falls im
naechsten Chat ein `ModuleNotFoundError: dotenv` auftritt: `pip install
python-dotenv` im aktivierten venv nachholen.

---

## 9. Wie man den aktuellen Stand sofort testet (fuer den naechsten Chat)

```powershell
cd G:\DAVID\Desktop\GitHub\Agentic_System
.\venv\Scripts\Activate
python -m agents.curator_agent.run_drift_check
```
Fuer normale Drift-Erkennung (nur neue Aenderungen seit letztem Snapshot).

```powershell
python -m agents.curator_agent.run_full_audit ROADMAP.md
```
Fuer den neuen Full-Audit-Modus (findet auch laenger bestehende
Widersprueche im gesamten Dokument, teurer an API-Calls).

Voraussetzungen: Ollama laeuft (fuer den Judge), `.env` mit
`GROQ_API_KEY` befuellt (fuer den Patch-Writer, aktuell einzige aktive
Cloud-Stufe), `AI_Project_Reviewer`-CLI ueber PATH erreichbar.

---

## 10. Kommunikations-/Arbeitsstil-Praeferenzen des Nutzers (unveraendert, weiterhin zwingend einzuhalten)

- Immer interaktiv, Frage-Antwort-Stil VOR grossen Code-Aenderungen.
- Bei stellenweisen Code-Patches (nicht ganze Datei): IMMER exakt
  angeben, welche Zeile/Funktion ersetzt wird — in dieser Session gab es
  einen realen `NameError`, weil eine stellenweise Anleitung nicht alle
  betroffenen Stellen abdeckte. **Lektion fuer den naechsten Chat: bei
  mehrdeutigen/mehrfachen Fundstellen lieber die GANZE Funktion neu
  ausgeben statt einzelner Zeilen-Diffs, wenn Unsicherheit ueber den
  exakten aktuellen Dateizustand besteht.**
- Nutzer ist kostenbewusst/lokal-first, aber "will es von Anfang an
  richtig und gescheit machen" — bei Zielkonflikten robuste Loesung
  bevorzugen und kurz begruenden.
- Nutzer moechte klare technische Erklaerungen ("warum genau ist das
  passiert"), nicht nur Fixes.
- Vor jedem potenziell schaedlichen Schreibvorgang: IMMER explizite
  Bestaetigung einholen — durchgehend eingehalten in dieser Session,
  auch fuer alle neuen Cloud-Eskalationsstufen und Full-Audit-Patches.
- Nutzer denkt aktiv ueber Architektur mit (Cloud-Eskalation, FCC-Repo,
  Chunking-Strategie) — Vorschlaege fachlich einordnen, nicht ungeprueft
  uebernehmen (siehe FCC-Ablehnung Abschnitt 6.1 als Beispiel dafuer,
  einen Nutzer-Vorschlag konstruktiv, aber kritisch zu pruefen, statt
  blind umzusetzen).
- **NEU in dieser Session:** Wenn ein Schwesterprojekt (`AI_Project_
  Reviewer`) angefasst wird, das als "fertig" galt: nur additive
  Verbesserungen, nichts Bestehendes verschlechtern — explizite,
  nicht verhandelbare Vorgabe fuer den naechsten Schritt (Abschnitt 5.3).
