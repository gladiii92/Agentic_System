"""
Einmaliges Debug-Skript -- NICHT Teil der Projektstruktur, nur zur
Fehlersuche fuer den mtime-Vergleichsbug (Chat-Verlauf 2026-08-23).
Bitte im Python-Interpreter mit aktiviertem venv ausfuehren, im Root
von Agentic_System.
"""
import json
from pathlib import Path

snap_dir = Path(r"G:\DAVID\Desktop\GitHub\Agentic_System\data\curator_snapshots\AI_Project_Reviewer")
files = sorted(snap_dir.glob("concept_summary_*.json"))

print(f"Gefundene Snapshots: {[f.name for f in files]}")

for f in files:
    data = json.loads(f.read_text(encoding="utf-8"))
    print(f"\n--- {f.name} ---")
    print("generated_at:", data.get("generated_at"))
    for path, mtime in data.get("source_file_mtimes", {}).items():
        if "ROADMAP" in path.upper():
            print("  ROADMAP mtime:", path, "->", mtime)
    for doc in data.get("document_summaries", []):
        if "ROADMAP" in doc["path"].upper():
            print("  ROADMAP summary:", doc["summary"][:150])
