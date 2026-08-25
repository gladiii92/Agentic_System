# Handover — Projekt "Agentic_System", Curator-Agent + Evaluator-Agent
Stand: 2026-08-25, ca. 08:10 CEST
Zweck: Dieses Dokument als ERSTE Nachricht im naechsten Chat einfuegen.
Es dokumentiert den kompletten Stand nach einer intensiven Bau- und
Debug-Session (2026-08-22 bis 2026-08-25), damit ohne erneuten Datei-
Upload direkt weitergearbeitet werden kann. Alle Dateiinhalte, Pfade,
Entscheidungen und offenen Punkte sind hier vollstaendig enthalten.

---

## 0. Projektkontext (Kurzfassung)

Der Nutzer (David, Lichtenfels/Bayern, DE) betreibt mehrere parallele
Software-/Business-Projekte und baut "Agentic_System" als kleine,
selbst orchestrierte Multi-Agenten-Software-Firma: der Nutzer selbst
als Ideengeber, spezialisierte KI-Agenten als ausfuehrende Kraft.

Repo-Pfad: `G:\DAVID\Desktop\GitHub\Agentic_System`
Schwesterprojekt (bereits fertig, liefert Bausteine): `AI_Project_Reviewer`
  Pfad: `G:\DAVID\Desktop\GitHub\AI_Project_Reviewer`
FIS-Obsidian-Vault (Founder Intelligence System), enthaelt die zu
pflegenden Projekt-Dokumente (ROADMAP.md, Worklogs etc.):
  Pfad: `G:\DAVID\Desktop\GitHub\Founder_Intelligence_System\04_PRODUCT_OS\01_PRODUCTS\AI_PROJECT_REVIEWER\`
Aktueller Test-Zieldateiname: `ROADMAP.md` in diesem Vault-Ordner.

Grundsatzentscheidungen aus Phase-0-Planung (unveraendert gueltig):
- Verwaltungs-Agent (Curator) + Bewertungs-Agent (Evaluator) werden
  PARALLEL gebaut, nicht nachgelagert -- Evaluator ist Querschnitts-
  Komponente, wird spaeter auch vom Builder-Agenten genutzt.
- Modell-Eskalation: lokal (Ollama) -> kostenlose Cloud-Modelle -> manuell
  (noch nicht gebaut, kommt erst nach stabilem Curator+Evaluator).
- LangGraph als Ziel-Framework fuer die Gesamt-Orchestrierung (noch NICHT
  eingebaut -- aktuell laeuft alles als einfaches Python-Skript ohne
  Graph-Framework, LangGraph-Migration ist ein SPAETERER Schritt).
- Human-in-the-Loop bleibt bei JEDEM Schreibvorgang bestehen, bis ueber
  viele echte Laeufe verifiziert ist, dass Vorschlaege zuverlaessig sind.
  Automatisches Schreiben ohne Bestaetigung ist explizit NICHT das
  aktuelle Ziel, sondern eine bewusste, spaetere Entscheidung.
- Rollout/Deployment bleibt immer manuell (gilt fuer spaetere Builder-
  Agent-Phase, aktuell noch nicht relevant).

---

## 1. Architektur-Uebersicht (aktueller Stand, 2026-08-25)

```
Agentic_System/
├── venv/                          (Python 3.11.9 venv, aktiviert mit .\venv\Scripts\Activate)
├── requirements.txt
├── .gitignore
├── README.md
├── config.py                      (noch kaum genutzt, siehe Abschnitt 6 "TODO")
├── data/
│   ├── curator_snapshots/AI_Project_Reviewer/
│   │   ├── concept_summary_<timestamp>.json   (JEDER Lauf, nie geloescht)
│   │   └── latest.json                         (immer aktuellster Stand)
│   └── rejection_history/
│       └── curator_agent.jsonl                 (JSONL, ein Eintrag pro Ablehnung)
├── agents/
│   ├── __init__.py
│   ├── curator_agent/
│   │   ├── __init__.py
│   │   ├── concept_loader.py       (unveraendert seit 2026-08-23, stabil)
│   │   ├── snapshot_store.py       (erweitert 2026-08-24: speichert jetzt
│   │   │                            auch raw_text_by_filename pro Snapshot)
│   │   ├── drift_diff.py           (Schicht 1: reiner mtime-Vergleich,
│   │   │                            unveraendert seit 2026-08-24 Fix)
│   │   ├── diff_presenter.py       (unveraendert, nutzt Pythons difflib
│   │   │                            fuer die finale Anzeige-Diffs)
│   │   └── run_drift_check.py      (Orchestrator, KOMPLETT NEU 2026-08-25,
│   │                                siehe Abschnitt 2 unten)
│   └── evaluator_agent/
│       ├── __init__.py
│       ├── drift_judge_prompt.py   (VERSION 4, 2026-08-25, Hunk-basiert +
│       │                            Severity-Kalibrierung, siehe Abschnitt 3)
│       ├── evaluator.py            (VERSION 3, 2026-08-25, Hunk-basiert)
│       ├── patch_writer_prompt.py  (NEU 2026-08-25)
│       ├── patch_writer.py         (NEU 2026-08-25)
│       └── rejection_history.py    (unveraendert seit 2026-08-24)
└── patching/                       (NEU 2026-08-25, komplett neuer Ordner)
    ├── __init__.py
    ├── diff_hunks.py                (deterministischer Diff via difflib)
    ├── patch_models.py              (ProposedPatch/ValidatedPatch/PatchApplicationResult)
    ├── patch_validator.py           (harte exact-match-Validierung)
    └── patch_applier.py             (reine String-Ersetzung)
```

### GELOESCHTE Module (siehe Abschnitt 5 fuer die Fehlergeschichte, warum):
- `agents/curator_agent/section_locator.py`
- `agents/curator_agent/embedding_filter.py`
- `agents/curator_agent/line_context_extractor.py`
- `agents/evaluator_agent/proposal_writer.py`
- `agents/evaluator_agent/proposal_writer_prompt.py`
- `agents/evaluator_agent/proposal_validation.py`

Diese fuenf/sechs Module existierten in Zwischenversionen und wurden alle
durch die finale, robustere Patch-Architektur (Abschnitt 2) ersetzt.
Falls sie noch im Repo liegen: koennen geloescht werden, werden von
nichts mehr importiert.

### requirements.txt (aktueller Soll-Stand):
```
langgraph>=0.2.0
langchain-ollama>=0.2.0
langchain-core>=0.3.0
python-dotenv>=1.0.0
pytest>=8.0.0
requests>=2.31.0
```
Hinweis: `sentence-transformers` und `numpy` wurden mit dem Embedding-
Filter-Modul entfernt (siehe Abschnitt 5) -- werden von keinem
verbliebenen Modul mehr gebraucht, koennen aus requirements.txt entfernt
werden, falls sie noch drinstehen.

---

## 2. Aktueller Ablauf (run_drift_check.py, Stand 2026-08-25)

Ausfuehrung: `python -m agents.curator_agent.run_drift_check` (venv muss
aktiviert sein: `.\venv\Scripts\Activate`, PowerShell zeigt dann `(venv)`
vor dem Prompt -- ohne das schlagen Imports fehl mit ModuleNotFoundError).

Schritt-fuer-Schritt:
1. **Frischer concept_summary-Lauf**: `concept_loader.refresh_and_load()`
   ruft per Subprocess `ai-review build-concept-summary <pfad> --yes`
   auf (siehe Abschnitt 4 fuer den vollen externen Vertrag zu
   AI_Project_Reviewer). Dauert ca. 1 Minute (mehrere Ollama-Aufrufe).
2. **Vorherigen Snapshot laden**: `snapshot_store.load_latest_snapshot_with_raw_texts()`
   liefert ConceptSummary + raw_text_by_filename (Dict[Dateiname, Text])
   des letzten gespeicherten Laufs. None beim allerersten Mal.
3. **Schicht 1 -- mtime-Diff**: `drift_diff.diff_concept_summaries()`
   vergleicht NUR source_file_mtimes zwischen altem und neuem Snapshot.
   Liefert Liste von DriftCandidate (Dateiname + alter/neuer summary-Text,
   OHNE eigene Bedeutung mehr fuer die Kandidatenauswahl -- reine
   Information). Kein Text-/Embedding-Vergleich mehr in dieser Schicht.
4. **Deterministischer Hunk-Diff** (NEU, ersetzt Embedding-Filter UND
   Zeilennummer-Judge komplett): fuer jede Kandidaten-Datei, deren
   previous_summary NICHT None ist (also kein komplett neues Dokument),
   wird `patching.diff_hunks.compute_diff_hunks(old_text, new_text)`
   aufgerufen. Das nutzt Pythons difflib.SequenceMatcher -- KEIN LLM,
   KEIN Embedding, 100% deterministisch. Liefert eine Liste von DiffHunk
   (exakte alte/neue Zeilenbereiche + 3 Zeilen Kontext davor/danach).
5. **Judge PRO HUNK**: `evaluator.run_drift_judge()` bekommt NUR einen
   einzelnen, bereits lokalisierten Hunk (als Diff-Text mit -/+ /Kontext-
   Zeilen), NICHT die ganze Datei. Liefert HunkJudgment:
   `is_meaningful` (bool), `is_supported` (bool -- True=kein Widerspruch),
   `severity` (LOW/MEDIUM/HIGH), `reasoning`, `contradiction_summary`.
   Modell: `qwen2.5-coder:latest` (siehe Abschnitt 5, A/B-getestet, fuer
   diese strukturierte Analyseaufgabe zuverlaessiger als qwen2.5:latest).
6. **Filterung**: `is_meaningful=False` -> sofort uebersprungen (trivial).
   `is_supported=True` -> sofort uebersprungen (kein Widerspruch).
   Nur wenn beides "es ist wichtig UND es ist nicht belegt" zutrifft,
   geht es weiter zum Scoring.
7. **Scoring**: `evaluator.score_judgment_heuristically()` -- bewaehrtes
   4-Kriterien-Schema (Faktentreue 0.4, Vollstaendigkeit 0.25, Konsistenz
   0.2, Sicherheit 0.15), Mindestwert 7.0 gewichtet UND kein Einzelkriterium
   unter 4.0. Severity->Score-Uebersetzung: LOW=5.0, MEDIUM=7.0, HIGH=9.0.
   **OFFENER KALIBRIERUNGSPUNKT** (siehe Abschnitt 6): Judge tendierte in
   Tests zu LOW auch bei eindeutig belegten Widerspruechen -- Prompt in
   Version 4 (2026-08-25) um explizite Severity-Ankerbeispiele ergaenzt,
   NOCH NICHT re-getestet (letzter Testlauf war noch mit Version 3-Prompt,
   ergab Score 6.20 < 7.0, faelschlich verworfen trotz korrekter Diagnose).
8. **Patch-Erzeugung**: NUR wenn approved=True: `patch_writer.write_patch()`
   bekommt denselben Hunk-Text + contradiction_summary, liefert
   `ProposedPatch(filename, exact_old_text, replacement_text, change_summary)`.
   Modell: `qwen2.5:latest` (Text-Variante, fuer Formulierungsaufgabe
   gewaehlt -- noch NICHT A/B-getestet gegen Coder-Variante fuer DIESE
   spezifische Patch-Aufgabe, nur fuer die alte Ganzdatei-/Abschnitts-
   Schreibaufgabe getestet).
9. **Patch-Validierung** (kritischste Sicherheitsschicht):
   `patching.patch_validator.validate_patch()` prueft: exact_old_text
   nicht leer, Mindest-/Maximallaenge, MUSS GENAU EINMAL wortwoertlich im
   aktuellen Dateitext vorkommen (0 oder >1 Treffer = automatische
   Ablehnung OHNE Anzeige), Laengenverhaeltnis replacement/original max.
   3x, keine Prompt-Leak-Marker-Phrasen, replacement != original.
10. **Anwendung + Human-in-the-Loop**: bei bestandener Validierung wird
    der Patch NUR IM SPEICHER angewendet (`patching.patch_applier.apply_patch()`,
    reine String-Ersetzung `text.replace(old, new, 1)`), als Diff
    angezeigt (`diff_presenter.build_unified_diff()`), und erst nach
    "ja"-Bestaetigung TATSAECHLICH auf die Platte geschrieben. Bei "nein"
    wird nach einem Pflicht-Ablehnungsgrund gefragt und in
    `rejection_history.record_rejection()` gespeichert (JSONL, siehe
    Abschnitt 1 Ordnerstruktur).
11. **Snapshot speichern**: `snapshot_store.save_snapshot()` wird IMMER
    erst am ALLERENDE von run() aufgerufen (siehe Abschnitt 5, Bugfix
    "Snapshot wurde faelschlich vor Fehlern gespeichert") -- Ausnahme:
    bei technischem Fehler in Schritt 1 (ConceptSummaryLoadError) wird
    GAR NICHT gespeichert, die alte Baseline bleibt gueltig.

---

## 3. Kernprinzip der finalen Architektur (WICHTIG, nicht wieder aufloesen)

Nach mehreren gescheiterten Zwischenversionen (siehe Abschnitt 5 fuer die
volle Fehlergeschichte) gilt seit 2026-08-25 folgendes NICHT-VERHANDELBARES
Prinzip, das JEDE kuenftige Aenderung an diesem System einhalten MUSS:

**Ein LLM darf NIEMALS frei formulierten Volltext zurueckgeben, der
direkt in eine Datei geschrieben wird.** Jede Schreiboperation MUSS ueber
das exact_old_text/replacement_text-Patch-Format laufen, dessen
Anwendbarkeit VOR jeder Anzeige/Anwendung deterministisch (Python-
String-Suche, kein LLM) verifiziert wird: exact_old_text muss WORTWOERTLICH
und GENAU EINMAL im Zieldokument vorkommen. Kommt er 0x oder >1x vor, wird
der Patch automatisch verworfen, OHNE dass der Nutzer ihn je sieht.

Ebenso darf ein LLM-Judge NIEMALS die ganze Datei gleichzeitig nach
Problemen durchsuchen (fuehrte zu Uebergeneralisierung: 10 identische
Fehlschluesse auf 10 verschiedene, thematisch aehnliche Zeilen in einem
einzigen Testlauf). Die Aenderungs-LOKALISIERUNG passiert IMMER zuerst
deterministisch (Pythons difflib zwischen zwei bekannten Textversionen),
das LLM bewertet danach nur noch EINEN bereits gefundenen, kleinen
Änderungsblock.

Wenn im naechsten Chat neue Schreibfunktionen fuer den Curator, oder
spaeter fuer den Builder-Agenten, gebaut werden: dieses Muster
(deterministisch lokalisieren -> LLM bewertet/formuliert nur einen
kleinen, bereits abgegrenzten Ausschnitt -> deterministisch validieren
-> Human-in-the-Loop -> deterministisch anwenden) MUSS wiederverwendet
werden, nicht neu erfunden.

---

## 4. Externer Vertrag zu AI_Project_Reviewer (WICHTIG, siehe concept_loader.py)

`agents/curator_agent/concept_loader.py` koppelt sich AUSSCHLIESSLICH per
Subprocess an AI_Project_Reviewer -- kein Code-Import, keine Kopie. Wenn
sich an AI_Project_Reviewer etwas aendert und der Curator ploetzlich nicht
mehr geht, HIER ZUERST NACHSEHEN, bevor im Curator-Code selbst gesucht wird:

1. CLI-Befehl muss aufrufbar bleiben: `ai-review build-concept-summary
   <projekt-pfad> --yes` (gefunden ueber System-PATH, NICHT ueber einen
   fest erwarteten venv-Pfad -- eine urspruengliche Annahme "venv/Scripts/
   ai-review.exe liegt im Repo" war FALSCH, siehe realer Test 2026-08-23;
   tatsaechlich lag es unter
   `C:\Users\Dave9\AppData\Local\Programs\Python\Python311\Scripts\ai-review.exe`).
2. Exit-Code-Vertrag: 0 = Erfolg, 1 = Fehler.
3. Ausgabe-Pfad: `data/exports/<slug>/concept_summary.json`, wobei slug =
   `project_name.strip().lower()` (klein geschrieben! nicht der
   Originalname mit Grossbuchstaben -- realer Fund 2026-08-23).
   JSON-Struktur: project_name, concept_text, document_summaries (Liste
   {path, summary}), generated_at, source_file_mtimes (Dict Vollpfad->mtime).
4. **KRITISCH, realer Bug 2026-08-23**: `data/exports/...` ist in
   AI_Project_Reviewer RELATIV zum cwd (current working directory) des
   Python-Prozesses aufgebaut, NICHT absolut zum eigenen Repo-Pfad. Der
   Subprocess-Aufruf in `run_concept_summary_refresh()` setzt deshalb
   BEWUSST `cwd=ai_project_reviewer_repo_path` -- wird das entfernt, landet
   die erzeugte Datei lautlos im FALSCHEN Ordner (Exit-Code bleibt 0,
   sieht erfolgreich aus, ist es aber nicht).
5. Ollama muss erreichbar sein (startet laut Nutzer-Setup automatisch mit
   Windows) -- wird von diesem Modul NICHT selbst geprueft, nur ueber den
   Exit-Code-Vertrag (Punkt 2) sichtbar.

---

## 5. Vollstaendige Fehlergeschichte dieser Session (2026-08-22 bis 25)

Diese Chronologie ist WICHTIG, damit im naechsten Chat nicht wieder
dieselben, bereits geloesten Fehler gemacht werden:

1. **PowerShell vs. Python-Konsole**: `from x import y` in PowerShell
   direkt eingegeben schlaegt fehl ("Schluesselwort wird nicht unterstuetzt").
   Erst `python` eingeben, DANN Python-Code einfuegen.
2. **ModuleNotFoundError trotz korrektem Pfad**: fehlende `__init__.py`
   in `agents/` und `agents/curator_agent/` -- Python erkennt Ordner ohne
   diese Datei nicht sicher als Package.
3. **generated_at blieb ueber mehrere Laeufe identisch**: siehe Punkt 4
   oben (cwd-Bug in AI_Project_Reviewer) -- der allererste, schwerste Bug,
   fuehrte dazu, dass ein kompletter Testzyklus scheinbar nichts fand.
4. **Export-Ordner-Slug klein geschrieben**: siehe Punkt 3 oben.
5. **13 von 13 Kandidaten waren reine Ollama-Formulierungsvarianz**:
   urspruenglicher Ansatz verglich Ollama-ZUSAMMENFASSUNGEN (2-3 Saetze)
   zwischen zwei Laeufen -- da Ollama nicht deterministisch neu formuliert,
   entstanden massenhaft falsche Kandidaten. FIX (mittlerweile durch
   Punkt 9 unten komplett obsolet): erst Embedding-Aehnlichkeit
   eingefuehrt, dann auf Rohtext-Vergleich umgestellt (Ollama-Zusammen-
   fassung als Vergleichsbasis fallengelassen).
6. **all-MiniLM-L6-v2 Token-Limit (256 Tokens)**: bei einem 7813-Zeichen-
   Dokument (~3002 Tokens) wurden nur die ersten ~8.5% embedded --
   eine Aenderung weiter hinten im Dokument wurde vom Embedding-Modell
   nie "gesehen", Aehnlichkeit faelschlich bei 1.000. FIX: Chunking mit
   Minimum-Aggregation ueber alle Chunk-Paare eingefuehrt (mittlerweile
   durch Punkt 9 komplett ersetzt, kein Embedding mehr im System).
7. **Snapshot wurde vor vollstaendigem, fehlerfreiem Durchlauf gespeichert**:
   ein Absturz in einer spaeteren Schicht (z.B. fehlendes Python-Paket)
   fuehrte trotzdem zum Speichern des neuen Snapshots als Baseline --
   der naechste Lauf "vergass" dadurch echte, noch unbearbeitete
   Kandidaten. FIX: save_snapshot() wird seither NUR am Ende von run()
   aufgerufen, nach allen Schritten, ausser bei technischem Fehler in
   Schritt 1.
8. **"Ganze Datei neu ausgeben"-Ansatz (Freitext-LLM-Schreiben)** fuehrte
   zu DREI unabhaengigen, realen Fehlern in aufeinanderfolgenden Tests:
   a) Mehrere unbeteiligte Abschnitte (Phasen 4-8) wurden durch
      identischen Platzhaltertext ersetzt, bereits abgeschlossene Phasen
      faelschlich auf "Offen" zurueckgesetzt.
   b) Der eigene Eingabeprompt wurde woertlich ins Ergebnis kopiert
      (Prompt-Leak).
   c) Abschnitts-Lokalisierung per Wortueberlappung (section_locator.py)
      waehlte den FALSCHEN Abschnitt ("MVP-Definition" statt der
      Phasen-Tabelle), weil thematisch aehnliche Woerter (Ruff, Bandit)
      in mehreren Abschnitten vorkommen -- zusaetzlich wurde beim
      Zusammenfuegen eine Trennlinie/Leerzeile geloescht, zwei Abschnitte
      verschmolzen optisch.
   d) Zeilengenauer Ansatz (Judge liefert Zeilennummern ueber die GANZE
      Datei) fuehrte zu massiver Uebergeneralisierung: EIN Fehlschluss
      ("Phase 3 abgeschlossen -> alle TODO-Zeilen im Merkposten-Abschnitt
      sind ebenfalls erledigt") wurde auf 10 verschiedene Zeilen desselben
      Abschnitts angewendet, alle mit identischem Fehlschluss.
   e) Selbst im kleinsten, zeilengenauen Kontext-Ausschnitt (5 Zeilen
      davor/danach) aenderte das Schreib-Modell ein voellig unbeteiligtes
      Wort ("eigenen" -> "own"), ohne jeden Bezug zum Auftrag -- ein
      reiner Modellfehler, den reine Laengen-/Zeilenzahl-Validierung nicht
      fangen konnte.
9. **FINALE LOESUNG (2026-08-25)**: kompletter Architektur-Umbau auf
   deterministischen Diff (Pythons difflib) statt LLM-basierter oder
   Embedding-basierter Lokalisierung, UND exact-match-Patch-Format statt
   Freitext-Schreiben. Siehe Abschnitt 2+3 fuer die Details. Dieser Ansatz
   hat im ersten Test (2026-08-25 morgens) fehlerfrei funktioniert: EIN
   korrekter Hunk gefunden (nicht mehr zehn falsche), Judge-Begruendung
   war inhaltlich richtig und praezise -- ABER Score fiel unter die
   Mindestschwelle wegen zu vorsichtiger LOW-Severity-Einstufung durch
   den Judge (siehe Abschnitt 6, noch offen).
10. **Modell-Wahl A/B-Test**: `qwen2.5-coder:latest` erkannte Drift in
    einem direkten Vergleichstest zuverlaessiger als `qwen2.5:latest`
    (Text-Variante) bei IDENTISCHEM Input -- Coder-Variante wurde deshalb
    fuer den Judge (Analyseaufgabe) beibehalten/zurueckgewechselt.
    Fuer die SCHREIB-Aufgabe (Formulierung) wurde qwen2.5:latest gewaehlt,
    aber dieser Vergleich ist WENIGER robust getestet als der Judge-
    Vergleich (siehe Abschnitt 6, offener Punkt).
11. **sentence-transformers Erstdownload-Warnung** ("unauthenticated
    requests to HF Hub"): reine Download-Rate-Limit-Warnung, KEIN
    Sicherheitsrisiko, keine Uebertragung von Projektinhalten. Mittlerweile
    ohnehin irrelevant, da Embedding-Ansatz komplett entfernt wurde
    (Punkt 9).

---

## 6. Offene Punkte / TODOs fuer den naechsten Chat (Prioritaet oben = zuerst)

1. **Severity-Kalibrierung erneut testen** (unmittelbar naechster Schritt):
   `drift_judge_prompt.py` Version 4 (2026-08-25) wurde bereits mit
   explizieren Severity-Ankerbeispielen ergaenzt (HIGH/MEDIUM/LOW klar
   definiert, Regel "eindeutig belegter Widerspruch ist NIEMALS LOW"),
   aber NOCH NICHT gegen einen echten Fall re-getestet. Naechster Schritt:
   dieselbe/aehnliche Aenderung an ROADMAP.md wiederholen (siehe Hinweis
   des Nutzers: "ich rede von der GESAMTprojektphase, nicht der einzelnen
   Zeile" -- ggf. muss der Testfall klarer/eindeutiger gewaehlt werden,
   z.B. eine Phase, die im Dokument WIEDERHOLT und UNMISSVERSTAENDLICH als
   "Offen" markiert ist, direkt widersprechen).
2. **A/B-Test Patch-Writer-Modell**: qwen2.5:latest vs. qwen2.5-coder:latest
   fuer die NEUE, viel kleinere Patch-Erzeugungsaufgabe (exact_old_text/
   replacement_text) wurde noch nicht durchgefuehrt -- nur fuer die
   inzwischen verworfenen, groesseren Schreibaufgaben (ganze Datei/
   Abschnitt/Zeilenkontext). Lohnt sich, weil die Aufgabe jetzt viel
   kleiner/praeziser ist als bei den fruehen Tests.
3. **Mehrere Hunks in einer Datei**: aktueller Code verarbeitet Hunks
   sequenziell in der Reihenfolge, in der difflib sie liefert (von oben
   nach unten im Dokument). Bei MEHREREN Hunks in einer Datei koennte
   ein frueh angewendeter Patch (String-Ersetzung) theoretisch die
   Grundlage fuer einen spaeteren Hunk-Vergleich veraendern, wenn beide
   sich ueberlappen -- bisher nur mit EINEM Hunk pro Testlauf getestet,
   Mehrfach-Hunk-Szenario noch nicht real verifiziert.
4. **LangGraph-Migration**: bisher komplett als sequenzielles Python-
   Skript ohne Graph-Framework gebaut (schneller zum Testen). Die
   urspruengliche Architektur-Entscheidung (Handover vom 2026-08-22) sah
   LangGraph als Ziel-Framework vor (Human-in-the-Loop als "first-class
   primitive", Checkpointing, conditional edges). Migration ist bewusst
   aufgeschoben, bis Curator+Evaluator inhaltlich zuverlaessig funktionieren
   -- sollte aber nicht dauerhaft vergessen werden.
5. **agentic_shared-Package**: frueh besprochen (Ollama-Client,
   Eskalationsmuster als eigenstaendiges, von AI_Project_Reviewer UND
   Agentic_System importierbares drittes Repo). NOCH NICHT umgesetzt --
   aktuell hat Agentic_System einen eigenen, minimalen Ollama-Aufruf-Code
   direkt in evaluator.py/patch_writer.py (kein geteiltes Package). Fuer
   Phase 1 bewusst so belassen (siehe urspruengliche Entscheidung:
   "Package spaeter, wenn sich zeigt, dass es sich lohnt").
6. **Eskalationskette (lokal -> OpenRouter -> manuell)**: noch NICHT
   gebaut. Aktuell nur Ollama, kein Fallback bei Fehlern (ausser
   Fehlermeldung). War immer als Phase 2 geplant (siehe Handover vom
   2026-08-22), nicht Teil von Phase 1.
7. **Neue Dokumente (previous_summary=None)**: werden aktuell in
   run_drift_check.py explizit UEBERSPRUNGEN ("kein Vorzustand fuer
   Hunk-Diff"). Phase 1 fokussiert bewusst nur auf ERKANNTE AENDERUNGEN
   an BESTEHENDEN Dokumenten, nicht auf Bewertung komplett neuer Dokumente.
   Ob/wie neue Dokumente kuenftig behandelt werden sollen, ist NICHT
   entschieden.
8. **config.py wird kaum genutzt**: FIS_VAULT_PATH und TEST_TARGET_FILE
   sind dort definiert, werden aber von run_drift_check.py aktuell NICHT
   importiert (dort stehen die Pfade als lokale Konstanten direkt im
   Modul). Sollte irgendwann konsolidiert werden, ist aber kein Blocker.
9. **Konsistenz-/Sicherheits-Scoring-Kriterien sind noch Platzhalter**:
   in `score_judgment_heuristically()` werden "konsistenz" (8.0) und
   "sicherheit" (9.0) aktuell mit FESTEN Werten und generischen
   Begruendungen belegt, nicht wirklich individuell bewertet. Nur
   "faktentreue" und "vollstaendigkeit" spiegeln das echte Judge-Urteil.
   Das war von Anfang an als bewusste Uebergangsloesung markiert (siehe
   TODO-Kommentar im Code), fuer Phase 1 ausreichend, aber noch nicht
   "fertig" im strengen Sinne.
10. **Evaluator als generische, wiederverwendbare Komponente fuer den
    spaeteren Builder-Agenten**: score_proposal()/CriterionScore sind
    bereits bewusst NICHT curator-spezifisch gestaltet (siehe Docstring
    in evaluator.py) -- wenn der Builder-Agent gebaut wird, sollte dessen
    Bewertung dieselbe Aggregations-/Schwellenwert-Logik nutzen, nur mit
    eigenen, builder-spezifischen CriterionScore-Werten.

---

## 7. Wie man den aktuellen Stand sofort testet (fuer den naechsten Chat)

```powershell
cd G:\DAVID\Desktop\GitHub\Agentic_System
.\venv\Scripts\Activate
python -m agents.curator_agent.run_drift_check
```

Voraussetzungen: Ollama laeuft (startet automatisch mit Windows laut
Nutzer-Setup), AI_Project_Reviewer-CLI ist ueber PATH erreichbar
(`ai-review` als Befehl funktioniert in einer normalen PowerShell,
unabhaengig vom Agentic_System-venv).

Fuer einen ECHTEN Testfall: eine Datei im FIS-Vault-Ordner (siehe
Abschnitt 0 fuer den Pfad) inhaltlich aendern (z.B. ROADMAP.md), dann den
Befehl ausfuehren. Bei "0 Kandidaten" wurde entweder nichts geaendert,
oder der letzte Lauf hat die Aenderung bereits als neue Baseline
gespeichert (siehe Fehlerpunkt 7 in Abschnitt 5 -- sollte durch den Fix
nicht mehr vorkommen, aber gut zu wissen, falls doch).

---

## 8. Kommunikations-/Arbeitsstil-Praeferenzen des Nutzers (wichtig!)

- Immer interaktiv, Frage-Antwort-Stil VOR grossen Code-Aenderungen --
  kein "einfach drauf losschreiben".
- Nutzer ist kostenbewusst/lokal-first, aber hat explizit gesagt: "Ich
  will es von Anfang an richtig und gescheit machen, auch wenn es
  aufwaendiger ist -- ich habe keine Lust, im Kreis zu drehen." Bei
  Zielkonflikten zwischen "schneller Fix" und "robuste Loesung": robuste
  Loesung bevorzugen, das explizit sagen und kurz begruenden.
- Nutzer moechte bei Unklarheiten oder Fehlern eine klare technische
  Erklaerung ("warum genau ist das passiert"), nicht nur "hier ist der
  Fix" -- Debugging-Prozess transparent nachvollziehbar halten.
- Vor jedem potenziell schaedlichen Schreibvorgang (echte Dateien im
  FIS-Vault): IMMER explizite Bestaetigung einholen, nie automatisch
  schreiben. Dieses Prinzip gilt als nicht verhandelbar fuer die aktuelle
  Phase.
- Der Nutzer denkt aktiv ueber Architektur mit (z.B. eigene Vorschlaege
  zu Chunking, zeilengenauer Lokalisierung) -- Vorschlaege ernst nehmen,
  fachlich einordnen (was ist bereits Best Practice, was ist ein neuer,
  guter Gedanke), nicht einfach uebernehmen ohne Bewertung.
