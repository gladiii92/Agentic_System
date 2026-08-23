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

   WICHTIG, real herausgefunden am 2026-08-23 (siehe Chat-Verlauf,
   Debug-Sitzung "generated_at bleibt identisch"): der Export-Pfad
   data/exports/... ist in AI_Project_Reviewer OFFENSICHTLICH RELATIV
   zum aktuellen Arbeitsverzeichnis (cwd) des Prozesses aufgebaut, NICHT
   absolut zum eigenen Repo-Pfad. Ein Subprocess-Aufruf OHNE explizites
   cwd=... landet die erzeugte Datei fälschlich im cwd des AUFRUFENDEN
   Prozesses (bei uns: Agentic_System), nicht im AI_Project_Reviewer-Repo
   selbst -- der Aufruf liefert trotzdem Exit-Code 0 und sieht komplett
   erfolgreich aus (Fehler bleibt STILL, siehe Vertragspunkt 2 oben: wir
   pruefen nur den Exit-Code, nicht den tatsaechlichen Schreibort).
   FIX: subprocess.run() bekommt deshalb explizit cwd=ai_project_reviewer_repo_path.
   Wenn sich dieses cwd-Verhalten in AI_Project_Reviewer jemals aendert
   (z.B. auf absolute Pfade umgestellt wird), bleibt unser expliziter
   cwd-Parameter trotzdem harmlos/korrekt -- kein Grund, ihn dann zu
   entfernen.

4. venv-Pfad-Annahme WAR FALSCH und wurde entfernt: die urspruengliche
   Annahme "venv/Scripts/ai-review.exe liegt im AI_Project_Reviewer-Repo"
   traf bei einem echten Test (2026-08-23) nicht zu (Pfad existierte
   nicht). Es wird jetzt bewusst NUR der blanke Befehl "ai-review" ueber
   den System-PATH verwendet -- funktioniert, WEIL/SOLANGE die
   AI_Project_Reviewer-venv beim Aufruf aktiviert bzw. im PATH sichtbar
   ist. Falls das kuenftig nicht mehr zutrifft: Fehlermeldung wird ueber
   FileNotFoundError sichtbar (siehe unten), keine stille Fehlfunktion.
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
    """Realer Test (2026-08-23) zeigt: AI_Project_Reviewer legt den Export-
    Ordner klein geschrieben mit Unterstrichen an (z.B. "ai_project_reviewer"
    fuer Projekt "AI_Project_Reviewer"), NICHT den Namen unveraendert. Windows
    ist zwar meist case-insensitiv im Dateisystem, aber wir bilden die
    tatsaechlich beobachtete Regel hier bewusst explizit nach, statt uns auf
    Windows-Case-Insensitivität zu verlassen (waere auf Linux/Mac falsch)."""
    return project_name.strip().lower()


def run_concept_summary_refresh(
    ai_project_reviewer_repo_path: Path,
    target_project_path: Path,
    timeout_seconds: int = 300,
) -> None:
    """Stoesst per Subprocess einen frischen build-concept-summary-Lauf an.

    Args:
        ai_project_reviewer_repo_path: Pfad zum AI_Project_Reviewer-Repo.
            Wird als cwd fuer den Subprocess verwendet (siehe Vertrag Punkt 3,
            cwd-Bugfix 2026-08-23) UND zur Herleitung des Export-Pfads in
            load_concept_summary().
        target_project_path: Pfad des Projekts, das zusammengefasst werden
            soll (z.B. wieder AI_Project_Reviewer selbst als Testfall, siehe
            Chat-Verlauf, oder spaeter ein anderes Projekt).
        timeout_seconds: Sicherheitsabbruch, falls Ollama haengt.

    Raises:
        ConceptSummaryLoadError: bei Exit-Code != 0 oder Timeout.
    """
    command = [
        CLI_COMMAND,
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
            cwd=str(ai_project_reviewer_repo_path),
        )
    except subprocess.TimeoutExpired as exc:
        raise ConceptSummaryLoadError(
            f"build-concept-summary Timeout nach {timeout_seconds}s. "
            f"Vermutlich haengt Ollama. Kommando: {' '.join(command)}"
        ) from exc
    except FileNotFoundError as exc:
        raise ConceptSummaryLoadError(
            f"CLI-Befehl '{CLI_COMMAND}' nicht gefunden. Ist die venv von "
            f"AI_Project_Reviewer aktiviert/im PATH? Siehe Vertrag-Kommentar "
            f"oben in diesem Modul (Punkt 4)."
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
