"""
Debug-Skript 2 -- prueft, ob unser Subprocess-Aufruf ueberhaupt dieselbe
concept_summary.json trifft/aktualisiert, die der manuelle CLI-Aufruf
erzeugt (Chat-Verlauf 2026-08-23, Fortsetzung des mtime-Bugs).
Im Python-Interpreter mit aktiviertem Agentic_System-venv ausfuehren.
"""
import json
from pathlib import Path

export_path = Path(r"G:\DAVID\Desktop\GitHub\AI_Project_Reviewer\data\exports\ai_project_reviewer\concept_summary.json")
print("Existiert (klein geschrieben)?", export_path.exists())
if export_path.exists():
    data = json.loads(export_path.read_text(encoding="utf-8"))
    print("generated_at laut Datei:", data.get("generated_at"))
    print("Anzahl Dokumente:", len(data.get("document_summaries", [])))

# Jetzt unseren eigenen Subprocess-Aufruf isoliert testen:
from agents.curator_agent.concept_loader import run_concept_summary_refresh

run_concept_summary_refresh(
    ai_project_reviewer_repo_path=Path(r"G:\DAVID\Desktop\GitHub\AI_Project_Reviewer"),
    target_project_path=Path(r"G:\DAVID\Desktop\GitHub\AI_Project_Reviewer"),
)

print("\nNach unserem Subprocess-Aufruf:")
data2 = json.loads(export_path.read_text(encoding="utf-8"))
print("generated_at laut Datei:", data2.get("generated_at"))
print("Anzahl Dokumente:", len(data2.get("document_summaries", [])))
