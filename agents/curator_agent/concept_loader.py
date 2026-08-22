"""
agents/curator_agent/concept_loader.py

Erster Baustein des Curator-Agenten (Phase 1). Zweck: den aktuellen,
inhaltlichen Ist-Zustand eines externen Projekts (hier zunaechst:
AI_Project_Reviewer) ueber dessen eigene CLI beschaffen und als Python-
Objekt bereitstellen. Enthaelt bewusst NOCH KEINE Drift-Erkennung, keinen
Ollama-Aufruf, keine History -- reine Grundlage, siehe Chat-Verlauf
2026-08-22.

================================================================================
!!! EXTERNER VERTRAG -- BEI AENDERUNGEN IN AI_Project_Reviewer BEACHTEN !!!
================================================================================
Dieses Modul koppelt sich AUSSCHLIESSLICH ueber einen Subprocess-Aufruf der
AI_Project_Reviewer-CLI an das fremde Projekt (bewusste Entscheidung, siehe
Chat-Verlauf 2026-08-22: loseste moegliche Kopplung, kein Code-Import, keine
Kopie). Das bedeutet: interne Refactorings in AI_Project_Reviewer sind
GEFAHRLOS, solange folgende drei Vertragspunkte erhalten bleiben. Wird einer
davon geaendert, MUSS dieses Modul (CLI_COMMAND unten) mit angepasst werden,
sonst bricht der Curator-Agent lautlos bzw. mit unklarer Fehlermeldung.

1. CLI-Befehl bleibt aufrufbar exakt als:
       ai-review build-concept-summary <projekt-pfad> --yes
   (Quelle: cli.py, Funktion build_concept_summary_command, Stand 2026-08-22)

2. Exit-Code-Vertrag bleibt: 0 = Erfolg, 1 = Fehler (z.B. Ollama nicht
   erreichbar, kein Vault-Ordner gefunden). Dieses Modul wertet NUR den
   Exit-Code aus, liest keine Stdout-Textmuster zur Erfolgspruefung.

3. Ausgabe-Pfad und JSON-Struktur bleiben:
       data/exports/<projekt-slug>/concept_summary.json
   mit mindestens den Feldern: project_name, concept_text,
   document_summaries (Liste von {path, summary}), generated_at,
   source_file_mtimes (Dict Pfad -> mtime-float).
   (Quelle: concept_summary.py / config.py, Stand 2026-08-22)

Wenn du in einem Jahr etwas an AI_Project_Reviewer aenderst und der Curator
ploetzlich nicht mehr geht: zuerst hier oben die drei Punkte pruefen, bevor
du im Curator-Code selbst suchst. Das ist der wahrscheinlichste Bruchpunkt.
================================================================================

Voraussetzung zur Laufzeit: Ollama muss erreichbar sein (laut Nutzer-Setup
startet Ollama automatisch mit Windows, siehe Chat-Verlauf 2026-08-22) --
dieses Modul prueft das NICHT selbst, sondern verlaesst sich auf den
Exit-Code-Vertrag oben (Punkt 2).
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path


CLI_COMMAND = "ai-review"
CLI_SUBCOMMAND = "build-concept-summary"


class ConceptSummaryLoadError(Exception):
    """Wird ausgeloest, wenn der CLI-Aufruf fehlschlaegt oder die erzeugte
    concept_summary.json nicht wie erwartet gelesen werden kann."""


@dataclass(frozen=True)
class DocumentSummary:
    path: str
    summary: str


@dataclass(frozen=True)
class ConceptSummary:
    """Python-Abbild einer concept_summary.json (siehe Vertrag Punkt 3 oben).
    Enthaelt bewusst nur die Felder, die der Curator-Agent tatsaechlich
    braucht -- nicht 1:1 die volle JSON-Struktur, um Aenderungen an
    Zusatzfeldern (z.B. "model") nicht mit durchzuschleppen."""

    project_name: str
    concept_text: str
    document_summaries: list[DocumentSummary]
    generated_at: str
    source_file_mtimes: dict[str, float]

    def summary_for(self, filename: str) -> DocumentSummary | None:
        """Sucht einen document_summaries-Eintrag ueber den Dateinamen
        (z.B. "ROADMAP.md"), unabhaengig vom vollen Pfad-Praefix."""
        for doc in self.document_summaries:
            if Path(doc.path).name == filename:
                return doc
        return None


def _project_slug(project_name: str) -> str:
    """Muss exakt dieselbe Slug-Logik wie AI_Project_Reviewer verwenden,
    sonst wird der Export-Ordner nicht gefunden. Quelle: cli.py,
    z.B. in findings_sync/review (project_name.strip().lower().replace(" ", "-")).
    Fuer build-concept-summary selbst wird der Projektname NICHT geslugt,
    sondern direkt scan_result.project_name als Ordnername unter
    data/exports/ verwendet (siehe exports_dir_for_project in config.py) --
    hier bewusst OHNE .lower()/.replace(), falls sich das als falsch
    herausstellt, siehe TODO-Test in tests/test_concept_loader.py."""
    return project_name.strip()


def run_concept_summary_refresh(
    ai_project_reviewer_repo_path: Path,
    target_project_path: Path,
    timeout_seconds: int = 300,
) -> None:
    """Stoesst per Subprocess einen frischen build-concept-summary-Lauf an.

    Args:
        ai_project_reviewer_repo_path: Pfad zum AI_Project_Reviewer-Repo,
            dessen aktivierte venv den "ai-review"-Befehl bereitstellt.
        target_project_path: Pfad des Projekts, das zusammengefasst werden
            soll (z.B. wieder AI_Project_Reviewer selbst als Testfall, siehe
            Chat-Verlauf, oder spaeter ein anderes Projekt).
        timeout_seconds: Sicherheitsabbruch, falls Ollama haengt.

    Raises:
        ConceptSummaryLoadError: bei Exit-Code != 0 oder Timeout.
    """
    venv_ai_review = ai_project_reviewer_repo_path / "venv" / "Scripts" / "ai-review.exe"
    executable = str(venv_ai_review) if venv_ai_review.exists() else CLI_COMMAND

    command = [
        executable,
        CLI_SUBCOMMAND,
        str(target_project_path),
        "--yes",
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ConceptSummaryLoadError(
            f"build-concept-summary Timeout nach {timeout_seconds}s. "
            f"Vermutlich haengt Ollama. Kommando: {' '.join(command)}"
        ) from exc
    except FileNotFoundError as exc:
        raise ConceptSummaryLoadError(
            f"CLI-Befehl '{executable}' nicht gefunden. Ist die venv von "
            f"AI_Project_Reviewer aktiviert/vorhanden? Siehe Vertrag-Kommentar "
            f"oben in diesem Modul."
        ) from exc

    if result.returncode != 0:
        raise ConceptSummaryLoadError(
            f"build-concept-summary fehlgeschlagen (Exit-Code {result.returncode}).\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def load_concept_summary(
    ai_project_reviewer_repo_path: Path,
    project_name: str,
) -> ConceptSummary:
    """Liest eine bereits erzeugte concept_summary.json ein (siehe Vertrag
    Punkt 3 oben). Ruft NICHT selbst run_concept_summary_refresh auf --
    bewusst getrennt, damit Tests/Aufrufer entscheiden koennen, ob ein
    frischer Lauf noetig ist oder der letzte Stand ausreicht."""
    slug = _project_slug(project_name)
    export_path = (
        ai_project_reviewer_repo_path
        / "data"
        / "exports"
        / slug
        / "concept_summary.json"
    )

    if not export_path.exists():
        raise ConceptSummaryLoadError(
            f"concept_summary.json nicht gefunden unter: {export_path}\n"
            f"Vermutlich muss zuerst run_concept_summary_refresh() ausgefuehrt "
            f"werden, oder der Projektname/Slug stimmt nicht (siehe "
            f"_project_slug-Kommentar in diesem Modul)."
        )

    try:
        raw = json.loads(export_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConceptSummaryLoadError(
            f"concept_summary.json unter {export_path} ist kein valides JSON."
        ) from exc

    try:
        document_summaries = [
            DocumentSummary(path=item["path"], summary=item["summary"])
            for item in raw["document_summaries"]
        ]
        return ConceptSummary(
            project_name=raw["project_name"],
            concept_text=raw["concept_text"],
            document_summaries=document_summaries,
            generated_at=raw["generated_at"],
            source_file_mtimes=raw["source_file_mtimes"],
        )
    except KeyError as exc:
        raise ConceptSummaryLoadError(
            f"concept_summary.json unter {export_path} fehlt erwartetes Feld: {exc}. "
            f"Siehe Vertrag Punkt 3 oben in diesem Modul -- hat sich die JSON-"
            f"Struktur in AI_Project_Reviewer geaendert?"
        ) from exc


def refresh_and_load(
    ai_project_reviewer_repo_path: Path,
    target_project_path: Path,
    project_name: str,
    timeout_seconds: int = 300,
) -> ConceptSummary:
    """Komfort-Funktion: erst frischen Lauf anstossen, dann Ergebnis laden.
    Das ist die Funktion, die der Curator-Agent im Normalfall aufrufen wird."""
    run_concept_summary_refresh(
        ai_project_reviewer_repo_path=ai_project_reviewer_repo_path,
        target_project_path=target_project_path,
        timeout_seconds=timeout_seconds,
    )
    return load_concept_summary(
        ai_project_reviewer_repo_path=ai_project_reviewer_repo_path,
        project_name=project_name,
    )
