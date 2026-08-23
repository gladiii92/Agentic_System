"""
Debug-Skript 3 -- zeigt den ROHEN subprocess.run()-Aufruf inkl. stdout/
stderr/returncode, um zu sehen, WARUM der Aufruf "erfolgreich" ist, aber
die Datei nicht aktualisiert (Chat-Verlauf 2026-08-23, Fortsetzung).
"""
import subprocess
from pathlib import Path

ai_project_reviewer_repo_path = Path(r"G:\DAVID\Desktop\GitHub\AI_Project_Reviewer")
target_project_path = ai_project_reviewer_repo_path

venv_ai_review = ai_project_reviewer_repo_path / "venv" / "Scripts" / "ai-review.exe"
print("Erwarteter venv-Pfad:", venv_ai_review)
print("Existiert dieser Pfad?", venv_ai_review.exists())

executable = str(venv_ai_review) if venv_ai_review.exists() else "ai-review"
print("Tatsaechlich verwendeter Befehl:", executable)

command = [executable, "build-concept-summary", str(target_project_path), "--yes"]
print("Vollstaendiges Kommando:", command)

result = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)

print("\nreturncode:", result.returncode)
print("\n--- STDOUT (letzte 2000 Zeichen) ---")
print(result.stdout[-2000:] if result.stdout else "(leer)")
print("\n--- STDERR (letzte 2000 Zeichen) ---")
print(result.stderr[-2000:] if result.stderr else "(leer)")
