# Handover — Projekt "Agenten-System" (Arbeitstitel), Planungsdokument Phase 0

Erstellt: 2026-08-22, ca. 15:00 CEST
Zweck: Dieses Dokument im naechsten Chat als ERSTE Nachricht einfuegen, wenn
mit dem Bau dieses NEUEN, EIGENSTAENDIGEN Projekts begonnen wird. Es
dokumentiert die vollstaendige Vision, alle Grundsatzentscheidungen und eine
realistische, phasenweise Bau-Reihenfolge. Dieses Dokument ist reine PLANUNG
— es wurde in dieser Session noch KEIN Code geschrieben.

Status: NICHT BEGONNEN. Vorgaenger-/Schwesterprojekt `AI_Project_Reviewer`
ist fertig (siehe `HANDOVER_2026-08-22_Obsidian_Sync_Abschluss.md`) und
liefert wichtige wiederverwendbare Bausteine fuer dieses neue Projekt
(siehe Abschnitt 3).

---

## 1. Die Vision (Nutzer-Formulierung, komprimiert)

Der Nutzer betreibt mehrere parallele Software-/Business-Projekte (u.a.
Trading-Automatisierung "Quant-Pipeline", Gemstone-Business, AI Project
Reviewer) und moechte langfristig eine Art "kleine Software-Firma, alleine
gemanaged": der Nutzer selbst als Hirn/Ideengeber, spezialisierte KI-Agenten
als ausfuehrende Kraefte. Vier Agenten-Rollen wurden identifiziert:

1. **Verwaltungs-Agent** — haelt das gesamte FIS-Obsidian-Vault sauber:
   erkennt veraltete Dokumente (z.B. eine wochenalte `ROADMAP.md`, die nicht
   mehr zum echten Projektstand passt), aktualisiert sie, pflegt Tags/Links
   (baut auf dem bereits fertigen AI-Reviewer-Obsidian-Sync auf, siehe
   Abschnitt 3), haelt Dashboards aktuell. Langfristiges Ziel: ein
   "Jarvis"-artiges taegliches Briefing ("was ist gelaufen, was steht an").
2. **Builder-Agent** — baut/erweitert Code an bestehenden oder neuen
   Projekten automatisch in einem Loop (Vorstufe bereits im AI-Reviewer-
   Feedback-Loop erkennbar, aber dort ist jeder Schritt noch manuell vom
   Nutzer bestaetigt).
3. **Bewertungs-Agent** — bewertet die Arbeit des Builder-Agenten
   kontinuierlich (Code-Qualitaet, Architektur, Testabdeckung), damit der
   Builder weiss, was verbessert werden muss. Laeuft laut Nutzer-Entscheidung
   PARALLEL zu allen anderen Agenten mit, nicht nachgelagert.
4. **(Spaeter) Marketing-/weitere Agenten** — nutzen dieselbe Vault-
   Wissensbasis, um z.B. zu lernen, welche Vermarktungsansaetze fuer welche
   Produkte funktioniert haben.

**Eskalationsprinzip (fuer ALLE Agenten gleich, siehe Abschnitt 4):** jeder
Agent versucht zuerst lokal (Ollama), dann kostenlose OpenRouter-Modelle,
und erst wenn beides nicht ausreicht, wird der Nutzer benachrichtigt, um
manuell ein Frontier-Modell (ChatGPT Pro / Perplexity Pro, Copy-Paste wie
beim bestehenden AI-Reviewer-Feedback-Loop) zu befragen und die Antwort
zurueck in den Loop zu geben.

**Ausrollen/Deployment bleibt IMMER ein manueller, gemeinsamer Schritt**
(Nutzer-Entscheidung, explizit NICHT automatisiert) — Agenten bauen und
testen, der Nutzer entscheidet ueber den produktiven Rollout.

---

## 2. Grundsatzentscheidungen (2026-08-22, verbindlich fuer die Planung)

### 2.1 Projekt-Setup
Eigenstaendiges neues Projekt, eigener Ordner, eigenes Git-Repository
(analog zu `AI_Project_Reviewer`). Bekommt einen eigenen FIS-Vault-Ordner
unter `04_PRODUCT_OS/01_PRODUCTS/<PROJEKTNAME>/`, sobald ein Name feststeht
(siehe Offene Frage in Abschnitt 8). Der AI-Reviewer selbst kann/soll spaeter
mit seinem bestehenden Watcher (`ai-review watch`) auch auf DIESES neue
Projekt angesetzt werden — langfristig soll das aber der Verwaltungs-Agent
selbst automatisch erledigen (Kandidat fuer eine spaetere Phase, nicht MVP).

### 2.2 Bau-Reihenfolge (Agent fuer Agent, nicht Ebene fuer alle gleichzeitig)
Bestaetigt vom Nutzer: **Verwaltungs-Agent zuerst, mit dem Bewertungs-Agenten
von Anfang an PARALLEL mitgebaut** (nicht nachtraeglich angeflanscht), dann
Builder-Agent, dann weitere. Begruendung des Nutzers: "wenn der
Bewertungsagent steht, ist ja schon die halbe Miete geschafft" — der
Bewertungs-Agent ist eine Querschnitts-Komponente, kein isolierter,
nachgelagerter Schritt.

**Praxisuebliches Muster hierzu (siehe Recherche, Abschnitt 4.3):** das ist
tatsaechlich Best Practice in 2026 (siehe Evaluierungs-Loop-Beschreibung:
"trace → detect failure via evaluator → human review → dataset → re-run →
compare → deploy" ist ein etabliertes, iteratives Muster, kein
nachtraeglicher Zusatz).

### 2.3 Modell-Eskalationsstrategie (fuer ALLE Agenten identisch)
Reihenfolge: (1) Lokal via Ollama → (2) Kostenlose OpenRouter-Modelle →
(3) Manuelle Eskalation an den Nutzer (Copy-Paste-Prompt, wie beim
bestehenden AI-Reviewer-Feedback-Loop, Antwort wird zurueck in den Loop
gespeist). Nutzer-Vorbehalt, explizit uebernommen: "muss aber getestet
werden, was am besten funktioniert" — diese Reihenfolge ist der Startpunkt,
keine unumstoessliche Festlegung.

### 2.4 Architektur-Framework: LangGraph (empfohlen, mit Begruendung)
Nach Recherche (August 2026, mehrere unabhaengige Quellen) wird **LangGraph**
empfohlen, nicht CrewAI oder AutoGen/Microsoft Agent Framework. Begruendung,
zugeschnitten auf die konkreten Anforderungen dieses Projekts:

- **Human-in-the-Loop ist ein "first-class primitive"** in LangGraph
  (Interrupts, durable State, Replay) — exakt das Eskalationsmuster aus
  2.3 (Agent haengt fest → Nutzer wird eingebunden → Loop geht weiter) ist
  ein Kernanwendungsfall, kein Sonderfall.
- **Explizite, typisierte State-Verwaltung mit Checkpointing** — wichtig,
  weil der Builder-/Bewertungs-Loop ueber laengere Zeitraeume (ggf. mit
  manueller Frontier-Modell-Unterbrechung dazwischen) konsistent bleiben
  muss, ohne Kontext zu verlieren.
- **Deterministische, bedingte Verzweigung (conditional edges)** passt zum
  gewuenschten Muster "Bewertungs-Agent entscheidet, ob Builder weitermachen
  darf oder eskalieren muss" — das ist ein Graph-Routing-Problem, kein
  offenes Konversationsproblem (wo CrewAI/AutoGen staerker waeren).
- **Direkt mit lokalem Ollama kompatibel** (`langchain-ollama`/`ChatOllama`),
  mehrere aktuelle Tutorials (August 2026) zeigen exakt das Muster
  "LangGraph + Ollama + optionaler Cloud-Fallback" — kein Neuland, etabliert.
- Nachteil, ehrlich benannt: steilere Lernkurve als CrewAI. Fuer ein Projekt,
  das laut Nutzer "die naechsten Jahre" tragen soll, ist das ein akzeptabler
  Tausch gegen Kontrolle/Auditierbarkeit.

**Bewusst NICHT gewaehlt:**
- **CrewAI** — schnellerer Einstieg, aber schwaechere native Human-in-the-
  Loop-Unterstuetzung laut Vergleichsdaten (August 2026), passt schlechter
  zum Eskalationsmuster.
- **AutoGen/Microsoft Agent Framework** — seit April 2026 in "maintenance
  mode" zugunsten des Microsoft Agent Framework, staerker auf offene,
  konversationelle Multi-Agent-Forschung ausgelegt statt auf deterministische,
  ueberwachte Produktions-Loops.
- **n8n** — als reine Workflow-Engine fuer EINEN einfachen Agenten
  (Trigger → LLM-Node → Tool-Node) attraktiv und schneller aufgesetzt, aber
  fuer mehrstufige, zustandsbehaftete Multi-Agenten-Kooperation (Verwaltung +
  Bewertung + Builder mit Rueckkopplung) weniger geeignet als ein
  Code-First-Graph-Framework. Kann spaeter als ERGAENZUNG dienen (z.B. fuer
  einfache Cron-Trigger/Benachrichtigungen), ersetzt aber nicht die
  Kern-Orchestrierung.

### 2.5 MVP-Definition (Agent-weise, nicht Gesamtsystem-weise)
Bestaetigt vom Nutzer: kein "Gesamtsystem-MVP", sondern klar abgegrenzte
Agenten-MVPs:
- **Verwaltungs-Agent-MVP:** identifiziert zuverlaessig MINDESTENS eine
  veraltete Vault-Datei (z.B. `ROADMAP.md`) und schlaegt eine konkrete
  Aktualisierung vor, die der Nutzer bestaetigt. Muss wiederholbar sein
  (nicht nur einmalig als Demo funktionieren).
- **Bewertungs-Agent-MVP:** liefert fuer eine gegebene Code-Aenderung/einen
  gegebenen Vault-Vorschlag eine nachvollziehbare, konsistente Bewertung
  ("perfekte Bewertung" laut Nutzer-Formulierung — zu praezisieren in
  Phase 1, siehe Abschnitt 6.2: was "gut bewertet" konkret heisst, muss
  messbar definiert werden, sonst bleibt es subjektiv).
- **Builder-Agent-MVP:** baut/aendert Code fuer eine klar umrissene,
  kleine Aufgabe, lässt Tests laufen, markiert sich selbst nur als
  "fertig", wenn Tests gruen sind (siehe 2.6).

### 2.6 Sicherheitsleitplanken fuer den Builder-Agenten (nicht verhandelbar)
- Arbeitet NIEMALS direkt auf `main`/dem Hauptbranch, sondern immer in
  einem separaten Branch oder einer Sandbox-Kopie.
- Muss Tests ausfuehren und BESTEHEN lassen, bevor er sich selbst als
  "fertig" markiert — kein Selbstabschluss ohne gruene Tests.
- Rollout/Deployment/Merge in den Hauptbranch bleibt manueller,
  gemeinsamer Schritt mit dem Nutzer (siehe Abschnitt 1, Vision).

---

## 3. Wiederverwendbare Bausteine aus dem AI-Reviewer-Projekt

Diese Bausteine muessen NICHT neu erfunden werden, sondern koennen als
Vorbild/direkt wiederverwendet werden (ggf. als eigenstaendige Bibliothek
ausgelagert, falls beide Projekte sie brauchen — zu entscheiden in Phase 1):

- **Manuelles Frontier-Modell-Eskalationsmuster** (`feedback_loop/loop_window.py`,
  `response_parser.py`, `chatgpt_prompt_builder.py`): Prompt bauen → Nutzer
  kopiert in ChatGPT Pro → Antwort wird zurueck geparst → Loop geht weiter.
  Exakt das Muster fuer Eskalationsstufe 3 (Abschnitt 2.3).
- **Ollama-Client mit klarer Fehlerbehandlung** (`ollama_client.py`):
  `OllamaConnectionError`/`OllamaTimeoutError`/`OllamaResponseError`/
  `OllamaJSONModeError` als sauberes Muster fuer Eskalationsstufe 1.
- **Obsidian-Vault-Interaktion** (`obsidian_export.py`, `concept_summary.py`):
  Kandidaten sammeln, Snippets extrahieren, TF-IDF-Ranking, Tags/Links
  parsen und schreiben — direkte Grundlage fuer den Verwaltungs-Agenten
  (siehe Abschnitt 6.1, dort wird die Erweiterung um "Aktualitaets-Check +
  Update-Vorschlag" beschrieben).
- **Human-in-the-Loop-Bestaetigungsmuster** (durchgehend im gesamten
  AI-Reviewer-Projekt): kein automatisches Schreiben ohne sichtbare
  Vorschau/Bestaetigung — gilt als Grundprinzip auch fuer dieses neue Projekt.
- **Static-Analysis-Runner-Pattern** (`ruff_runner.py`, `bandit_runner.py`):
  Vorbild fuer den Bewertungs-Agenten (Abschnitt 6.2) — deterministische,
  KI-freie Code-Qualitaetssignale als EIN Baustein der Gesamtbewertung,
  nicht die einzige Quelle.

---

## 4. Recherche-Ergebnisse zur Architektur-Entscheidung (Stand August 2026)

### 4.1 Framework-Vergleich (Kernaussagen mehrerer unabhaengiger Quellen)
- LangGraph: graph-basierte State Machine, explizites typisiertes State-
  Objekt mit Checkpointing, staerkste Tracing-/Debugging-Unterstuetzung
  (LangSmith-Integration), steilste Lernkurve, gilt uebereinstimmend als
  "production standard for reliability-critical applications".
- CrewAI: Rollen-basierte "Crews", schnellster Einstieg, sanftere
  Lernkurve, schwaecheres natives Human-in-the-Loop.
- AutoGen: seit April 2026 offiziell in "maintenance mode", abgeloest durch
  Microsoft Agent Framework 1.0 — fuer neue Projekte nicht mehr empfohlen.

### 4.2 OpenRouter kostenlose Modelle (Stand August 2026, Beispiele)
Mehrere aktuelle produktionsreife Modelle mit `:free`-Tag verfuegbar, u.a.
Modelle mit Fokus auf agentisches Coding (z.B. Poolside Laguna-Reihe,
Cohere North Mini Code) und auf Langzeit-Reasoning/Orchestrierung
(z.B. NVIDIA Nemotron-3-Reihe, teilweise mit sehr grossem Kontextfenster
bis 1M Tokens). Genaue Modellwahl pro Agent muss in Phase 1/3 experimentell
geprueft werden (Modelllandschaft aendert sich schnell) — dieses Dokument
legt nur die STRATEGIE fest (lokal → kostenlos-cloud → manuell), nicht ein
fixes Modell.

### 4.3 Bewertungs-Loop als etabliertes Muster
Der von unabhaengigen Quellen beschriebene Standard-Verbesserungs-Loop
deckt sich mit der Nutzer-Vision: Trace erzeugen → Fehler per Evaluator
erkennen → an menschliche Pruefung routen → validierten Fehlerfall in
Testdatensatz aufnehmen → Aenderung vornehmen (Prompt/Modell/Agent-Design)
→ gegen Datensatz testen → mit Produktivversion vergleichen → Freigabe-
Schwelle anwenden → ausrollen. Relevant fuer Abschnitt 6.2 (Bewertungs-Agent
braucht von Anfang an einen wachsenden, konkreten Testfall-/Beispiel-
Datensatz, nicht nur Ad-hoc-Urteile).

### 4.4 Grenzen des aktuell technisch Machbaren (ehrlich, Stand Juli 2026)
Eine Quelle (Augment, Autonomous Engineering Loop) ordnet den Stand der
Technik so ein: Planung/Task-Zerlegung, Multi-File-Code-Schreiben, erste
Testgenerierung, Bug-Reproduktion/-Fix und PR-Erstellung gelten als
"reliably autonomous" moeglich — **Merge-Entscheidung und Produktiv-
Deployment gelten explizit NICHT als autonom bestaetigt** (Stand Juli 2026).
Das deckt sich exakt mit der Nutzer-Entscheidung, Rollout manuell zu halten
(Abschnitt 1) — keine Anpassung noetig, aber gute Bestaetigung, dass diese
Grenze realistisch und nicht zu konservativ gezogen ist.

---

## 5. Technischer Grundaufbau (Vorschlag, im naechsten Chat zu verfeinern)

```
Agenten-System (neues Repo)
├── agents/
│   ├── curator_agent/      # Verwaltungs-Agent (Phase 1)
│   ├── evaluator_agent/    # Bewertungs-Agent (Phase 1, parallel)
│   ├── builder_agent/      # Builder-Agent (Phase 2)
│   └── shared/             # gemeinsame Bausteine (Modell-Eskalation,
│                           # Ollama-Client, Obsidian-Interaktion --
│                           # ggf. Wiederverwendung/Fork aus AI_Project_Reviewer
├── graphs/                 # LangGraph-Definitionen (State, Nodes, Edges)
├── escalation/             # Eskalationsstufen-Logik (lokal -> OpenRouter
│                           # -> manuelles Frontier-Modell-Fenster,
│                           # analog zu feedback_loop/loop_window.py)
├── config.py                # Vault-Pfade, Modell-Konfiguration, etc.
└── tests/
```

**Hinweis:** Dies ist ein GROBER Vorschlag zur Orientierung, keine finale
Festlegung — die genaue Modul-Struktur wird zu Beginn von Phase 1 im
Detail besprochen (Frage-Antwort-Stil, wie bisher in diesem Projekt
gehandhabt).

---

## 6. Phasenplan (detailliert)

### PHASE 0 — Planung (DIESE SESSION, abgeschlossen)
Vision festgehalten, Grundsatzentscheidungen getroffen, Architektur
recherchiert und begruendet ausgewaehlt. Kein Code.

### PHASE 1 — Verwaltungs-Agent (Curator) + Bewertungs-Agent (Evaluator), MVP
**Ziel (siehe 2.5):** Verwaltungs-Agent erkennt zuverlaessig mindestens eine
veraltete Vault-Datei und schlaegt eine Aktualisierung vor (Nutzer
bestaetigt); Bewertungs-Agent liefert dazu eine nachvollziehbare Bewertung.

**Zu klaerende Fragen zu Beginn von Phase 1 (noch NICHT in dieser Session
entschieden, im naechsten Chat als Erstes zu besprechen):**
1. Wie wird "veraltet" konkret definiert? Rein zeitbasiert (Mtime seit X
   Tagen)? Inhaltlich (Konzept-Zusammenfassung vs. tatsaechlicher aktueller
   Code-/Projektstand, Abgleich noetig)? Eine Kombination?
2. Woher bezieht der Verwaltungs-Agent den "aktuellen Stand" eines externen
   Projekts, um zu pruefen, ob eine Vault-Datei noch stimmt? (Vermutlich:
   Wiederverwendung/Erweiterung von `concept_summary.py`-Logik aus dem
   AI-Reviewer, die ja bereits Projekt-Vault-Dokumente einliest — aber hier
   fehlt noch der Abgleich "Vault-Text vs. echter Code-Stand".)
3. Was genau bedeutet "perfekte Bewertung" fuer den Bewertungs-Agenten
   messbar? Es braucht ein konkretes Bewertungsschema (z.B. Kriterien-Liste
   mit Gewichtung), sonst bleibt "gut/schlecht" subjektiv und nicht
   reproduzierbar.
4. Architektur-Detailfrage: laeuft der Bewertungs-Agent als eigener
   LangGraph-Node, der die Vorschlaege des Verwaltungs-Agenten VOR der
   Nutzer-Bestaetigung filtert/bewertet (wie in der Nutzer-Frage
   angedeutet: "ein Bewertungsagent der die Entscheidungen rausfiltert"),
   oder als nachgelagerter, unabhaengiger Schritt?

**Wiederverwendung aus AI-Reviewer:** `obsidian_export.py`-Snippet-
Extraktion, `concept_summary.py`-Ollama-Pipeline-Muster, Human-in-the-Loop-
Bestaetigungsmuster.

### PHASE 2 — Eskalationsmechanismus als eigenstaendiger, getesteter Baustein
**Ziel:** Bevor der Builder-Agent gebaut wird, muss die Eskalationskette
(lokal → OpenRouter kostenlos → manuell) als EIGENSTAENDIGER, wiederver-
wendbarer Baustein stehen und mit dem bereits fertigen Verwaltungs-/
Bewertungs-Agenten-Paar getestet sein. Grund: alle folgenden Agenten
nutzen dieselbe Eskalationslogik — sie einmal sauber zu bauen, verhindert
Drei-fache Doppelarbeit.

**Zu klaeren:** konkrete OpenRouter-Modellauswahl testen (siehe 4.2, Liste
aendert sich schnell), Fenster-UI fuer Stufe 3 (vermutlich Wiederverwendung/
Anpassung von `loop_window.py`-Stil).

### PHASE 3 — Builder-Agent, MVP
**Ziel (siehe 2.5):** baut/aendert Code fuer eine klar umrissene, kleine
Aufgabe an einem echten Projekt (voraussichtlich zuerst am AI-Reviewer
selbst als "Trockenuebung", da dessen Code/Tests bereits gut bekannt sind),
mit Pflicht-Tests vor Selbstabschluss (siehe 2.6).

**Zu klaeren:** welches konkrete Test-/Sandbox-Setup (separater Branch?
Docker-Sandbox? — siehe Recherche 4.4, OpenHands nutzt z.B. optionale
Docker-Sandbox), wie der Bewertungs-Agent hier konkret eingebunden wird
(gleiche Kriterien wie Phase 1, oder Code-spezifisch erweitert?).

### PHASE 4 — Zusammenspiel Verwaltungs- + Bewertungs- + Builder-Agent
**Ziel:** vollstaendiger Loop an einem echten, kleinen Projekt einmal
end-to-end durchlaufen lassen: Verwaltungs-Agent erkennt Handlungsbedarf →
Bewertungs-Agent bewertet/filtert → Builder-Agent setzt um → Bewertungs-
Agent prueft das Ergebnis → bei Blockade Eskalation → Nutzer bestaetigt
Rollout.

### PHASE 5 (spaeter, nicht Teil der initialen Roadmap) — Marketing-Agent,
"Jarvis"-Briefing, Mehrfach-Projekt-Orchestrierung
Bewusst NICHT Teil der detaillierten Planung dieser Session — wird erst
sinnvoll planbar, wenn Phasen 1-4 real funktionieren und zeigen, welche
Muster tatsaechlich tragen.

---

## 7. Kernprinzipien fuer dieses Projekt (uebernommen aus AI-Reviewer-Praxis)

- Vor jeder Code-Implementierung: interaktive Frage-Antwort-Klaerung, kein
  ungefragtes Losschreiben (gilt explizit auch fuer den naechsten Chat).
- Reale Tests mit echten Daten/echten Projekten bevorzugt gegenueber rein
  theoretischer Planung — jede Phase braucht einen echten Verifikations-
  Schritt, bevor sie als "fertig" gilt.
- Human-in-the-Loop bleibt overall bestehen, insbesondere bei Rollout/
  Deployment (siehe 2.6) — Autonomie waechst schrittweise, wird nicht von
  Anfang an vorausgesetzt.
- Kein Ebenen-Sprung: Builder-Agent wird nicht vor einem stehenden
  Verwaltungs-/Bewertungs-Agenten-Paar begonnen.

---

## 8. Offene Fragen fuer den Beginn der naechsten Session

1. Wie soll das neue Projekt heissen (Arbeitstitel fuer Repo-Name und
   FIS-Vault-Ordner)?
2. Beginnen wir Phase 1 direkt mit echten Vault-Dateien des AI-Reviewer-
   Projekts als Testfall (z.B. genau die genannte `ROADMAP.md`), oder mit
   einem kleineren, kuenstlichen Testszenario zuerst?
3. Soll `shared/`-Code (Ollama-Client, Eskalationsmuster) aus dem
   AI-Reviewer-Projekt per Copy/Fork uebernommen werden, oder als
   eigenstaendiges, von beiden Projekten importierbares Package ausgelagert
   werden (sauberer, aber mehr Infrastruktur-Aufwand vorab)?
4. Konkrete Beantwortung der vier Phase-1-Fragen aus Abschnitt 6.1 (Definition
   "veraltet", Abgleichsquelle fuer echten Projektstand, Bewertungsschema,
   Filter- vs. nachgelagerte Rolle des Bewertungs-Agenten).
