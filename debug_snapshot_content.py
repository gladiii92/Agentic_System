"""
Debug-Skript 4 -- prueft, ob der aktuell gespeicherte Snapshot tatsaechlich
den NEUEN (geaenderten) Dateiinhalt enthaelt, oder ob wir versehentlich
eine veraltete Version lesen (Chat-Verlauf 2026-08-24, Rohtext-Aehnlichkeit
1.000 trotz behaupteter Aenderung).
"""
import json
from pathlib import Path

snap_dir = Path(r"G:\DAVID\Desktop\GitHub\Agentic_System\data\curator_snapshots\AI_Project_Reviewer")
latest = snap_dir / "latest.json"

data = json.loads(latest.read_text(encoding="utf-8"))
print("generated_at im Snapshot:", data.get("generated_at"))

raw_texts = data.get("raw_text_by_filename", {})
print("\nROADMAP.md im Snapshot (letzte 300 Zeichen):")
print(repr(raw_texts.get("ROADMAP.md", "NICHT GEFUNDEN")[-300:]))

# Jetzt den ECHTEN, aktuellen Dateiinhalt direkt von der Platte lesen:
for full_path in data.get("source_file_mtimes", {}):
    if "ROADMAP" in full_path.upper():
        actual_path = Path(full_path)
        print(f"\nEchter Pfad: {actual_path}")
        print("Existiert?", actual_path.exists())
        if actual_path.exists():
            actual_text = actual_path.read_text(encoding="utf-8")
            print("Echter aktueller Inhalt (letzte 300 Zeichen):")
            print(repr(actual_text[-300:]))
            print("\nIst Snapshot-Text == echter Text?", raw_texts.get("ROADMAP.md") == actual_text)
