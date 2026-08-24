"""
Debug-Skript 5 -- isolierter Test: bekommt embedding_filter.py ueberhaupt
die RICHTIGEN previous_raw_texts und current_raw_texts uebergeben, oder
vergleichen wir versehentlich denselben Text mit sich selbst?
(Chat-Verlauf 2026-08-24, Rohtext-Aehnlichkeit 1.000 trotz sichtbarer
Aenderung "Phase 8 wurde abgeschlossen")
"""
from pathlib import Path
from agents.curator_agent.concept_loader import refresh_and_load
from agents.curator_agent.snapshot_store import load_latest_snapshot_with_raw_texts

AI_PROJECT_REVIEWER_REPO_PATH = Path(r"G:\DAVID\Desktop\GitHub\AI_Project_Reviewer")
CURATOR_DATA_ROOT = Path(r"G:\DAVID\Desktop\GitHub\Agentic_System\data")

current_summary = refresh_and_load(
    ai_project_reviewer_repo_path=AI_PROJECT_REVIEWER_REPO_PATH,
    target_project_path=AI_PROJECT_REVIEWER_REPO_PATH,
    project_name="AI_Project_Reviewer",
)

current_raw_texts = {}
for full_path in current_summary.source_file_mtimes:
    filename = Path(full_path).name
    current_raw_texts[filename] = Path(full_path).read_text(encoding="utf-8")

previous_summary, previous_raw_texts = load_latest_snapshot_with_raw_texts(
    CURATOR_DATA_ROOT, "AI_Project_Reviewer"
)

print("Enthaelt 'Phase 8' im AKTUELLEN Rohtext?", "Phase 8" in current_raw_texts.get("ROADMAP.md", ""))
print("Enthaelt 'Phase 8' im VORHERIGEN (gespeicherten) Rohtext?", "Phase 8" in previous_raw_texts.get("ROADMAP.md", ""))

print("\nLaenge aktueller Text:", len(current_raw_texts.get("ROADMAP.md", "")))
print("Laenge vorheriger Text:", len(previous_raw_texts.get("ROADMAP.md", "")))

print("\nSind beide Texte identisch (==)?", current_raw_texts.get("ROADMAP.md") == previous_raw_texts.get("ROADMAP.md"))
