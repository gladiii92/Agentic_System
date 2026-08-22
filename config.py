"""
Zentrale Konfiguration fuer Agentic_System.
Pfade und Modell-Einstellungen werden hier gesammelt, damit Module
(curator_agent, evaluator_agent, ...) keine Pfade/Config selbst
hart codieren -- wichtig fuer spaetere Entkopplung (siehe Chat-Diskussion
zu Standalone-Faehigkeit).
"""

from pathlib import Path

# TODO gemeinsam anpassen: echter Pfad zum FIS-Obsidian-Vault
FIS_VAULT_PATH = Path(r"G:\DAVID\Desktop\GitHub\AI_Project_Reviewer")

# TODO gemeinsam anpassen: konkrete Testfall-Datei fuer Phase 1
TEST_TARGET_FILE = FIS_VAULT_PATH / "ROADMAP.md"

OLLAMA_MODEL = "llama3.1"  # Platzhalter, wird in Phase 1/2 getestet
