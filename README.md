# Agentic_System

Multi-Agenten-System (Curator, Evaluator, Builder) zur automatisierten
Pflege und Weiterentwicklung von Software-Projekten und deren
Obsidian-Vault-Dokumentation.

## Status
Phase 1 in Arbeit: Curator-Agent (Drift-Erkennung im FIS-Vault) +
Evaluator-Agent (Bewertung/Filterung von Curator-Vorschlaegen), parallel
gebaut.

## Architektur
Siehe HANDOVER_2026-08-22_Agenten_System_Planung.md fuer die volle
Planungsgrundlage (Vision, Grundsatzentscheidungen, Phasenplan).

## Setup
1. `python -m venv venv`
2. `.\venv\Scripts\Activate` (Windows) 
3. `pip install -r requirements.txt`

## Struktur
- `agents/curator_agent/` — Drift-Erkennung, Vault-Update-Vorschlaege
- `agents/evaluator_agent/` — Bewertung/Filterung der Curator-Vorschlaege
- `graphs/` — LangGraph State-Machine-Definitionen
- `escalation/` — Modell-Eskalationskette (lokal -> OpenRouter -> manuell)
- `tests/` — Testfaelle
