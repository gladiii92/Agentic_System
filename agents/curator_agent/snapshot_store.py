"""
agents/curator_agent/snapshot_store.py

Zweiter Baustein des Curator-Agenten (Phase 1). Zweck: eine EIGENE,
vom AI_Project_Reviewer-Repo komplett unabhaengige Historie von
ConceptSummary-Stand (siehe concept_loader.py) fuehren, damit spaeter
Drift zwischen zwei Laeufen erkannt werden kann.

Bewusste Design-Entscheidungen (siehe Chat-Verlauf 2026-08-23):
- Alle Snapshots werden dauerhaft aufbewahrt, keine automatische
  Loeschung -- Dateien sind klein (wenige KB), volle Nachvollziehbarkeit
  ist wichtiger als Speicherplatz-Ersparnis in dieser Phase.
- "Vorheriger Snapshot" = immer der zuletzt gespeicherte Lauf, unabhaengig
  vom Zeitabstand. Keine Mindestzeitspanne-Logik.
- Curator wird aktuell rein MANUELL angestossen (kein Cron/Task Scheduler
  in dieser Phase, siehe Chat-Verlauf 2026-08-23) -- dieses Modul selbst
  ist davon unabhaengig und wuerde auch bei automatischer Taktung
  unveraendert funktionieren.

Speicherort (getrennt vom AI_Project_Reviewer-Repo, siehe Kopplungs-
Prinzip aus concept_loader.py):
    Agentic_System/data/curator_snapshots/<projekt-name>/
        concept_summary_<UTC-Zeitstempel>.json   (ein File pro Lauf)
        latest.json                               (Kopie des neuesten Laufs)
"""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from agents.curator_agent.concept_loader import ConceptSummary, DocumentSummary


class SnapshotStoreError(Exception):
    """Fehler beim Speichern/Laden eines Curator-Snapshots."""


def _snapshots_dir(curator_data_root: Path, project_name: str) -> Path:
    return curator_data_root / "curator_snapshots" / project_name.strip()


def _concept_summary_to_dict(summary: ConceptSummary) -> dict:
    return {
        "project_name": summary.project_name,
        "concept_text": summary.concept_text,
        "document_summaries": [asdict(doc) for doc in summary.document_summaries],
        "generated_at": summary.generated_at,
        "source_file_mtimes": summary.source_file_mtimes,
    }


def _concept_summary_from_dict(data: dict) -> ConceptSummary:
    document_summaries = [
        DocumentSummary(path=item["path"], summary=item["summary"])
        for item in data["document_summaries"]
    ]
    return ConceptSummary(
        project_name=data["project_name"],
        concept_text=data["concept_text"],
        document_summaries=document_summaries,
        generated_at=data["generated_at"],
        source_file_mtimes=data["source_file_mtimes"],
    )


def save_snapshot(
    curator_data_root: Path,
    project_name: str,
    summary: ConceptSummary,
) -> Path:
    """Speichert den aktuellen ConceptSummary-Stand als neuen, zeitgestempelten
    Snapshot UND aktualisiert latest.json. Ueberschreibt NIEMALS vorherige
    zeitgestempelte Snapshots -- nur latest.json wird jedes Mal ersetzt.

    Returns:
        Pfad zur neu erzeugten zeitgestempelten Snapshot-Datei.
    """
    target_dir = _snapshots_dir(curator_data_root, project_name)
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    snapshot_path = target_dir / f"concept_summary_{timestamp}.json"
    latest_path = target_dir / "latest.json"

    payload = json.dumps(_concept_summary_to_dict(summary), indent=2, ensure_ascii=False)

    # Absichtlich zuerst die zeitgestempelte Datei schreiben, DANACH latest.json --
    # falls der Prozess dazwischen abbricht, existiert wenigstens der
    # vollstaendige historische Snapshot, latest.json bleibt im schlimmsten
    # Fall nur einen Lauf hinter der Wahrheit zurueck (kein Datenverlust).
    snapshot_path.write_text(payload, encoding="utf-8")
    latest_path.write_text(payload, encoding="utf-8")

    return snapshot_path


def load_latest_snapshot(
    curator_data_root: Path,
    project_name: str,
) -> ConceptSummary | None:
    """Laedt den zuletzt gespeicherten Snapshot (latest.json). Gibt None
    zurueck, wenn noch nie ein Snapshot fuer dieses Projekt gespeichert wurde
    -- das ist der erwartete, normale Zustand beim allerersten Lauf, kein
    Fehler."""
    latest_path = _snapshots_dir(curator_data_root, project_name) / "latest.json"

    if not latest_path.exists():
        return None

    try:
        data = json.loads(latest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SnapshotStoreError(
            f"latest.json unter {latest_path} ist beschaedigt (kein valides JSON)."
        ) from exc

    try:
        return _concept_summary_from_dict(data)
    except KeyError as exc:
        raise SnapshotStoreError(
            f"latest.json unter {latest_path} fehlt erwartetes Feld: {exc}."
        ) from exc


def list_all_snapshots(curator_data_root: Path, project_name: str) -> list[Path]:
    """Listet alle zeitgestempelten Snapshot-Dateien (NICHT latest.json),
    sortiert von aeltestem zu neuestem. Nuetzlich fuer spaetere Auswertungen
    ueber mehrere Laeufe hinweg (z.B. "wie oft hat sich ROADMAP.md-Drift
    wiederholt")."""
    target_dir = _snapshots_dir(curator_data_root, project_name)
    if not target_dir.exists():
        return []
    return sorted(target_dir.glob("concept_summary_*.json"))
