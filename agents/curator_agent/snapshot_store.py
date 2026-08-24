"""
agents/curator_agent/snapshot_store.py

Zweiter Baustein des Curator-Agenten (Phase 1), erweitert am 2026-08-24
(siehe Chat-Verlauf: Notwendigkeit fuer echten Rohtext-zu-Rohtext-Vergleich
in embedding_filter.py, statt nur Zusammenfassung-zu-Rohtext-Naeherung).

NEU: Snapshots speichern jetzt ZUSAETZLICH den vollstaendigen Rohtext jeder
Vault-Datei zum Zeitpunkt des Snapshots (raw_text_by_filename), nicht nur
die Ollama-Zusammenfassung. Dadurch kann embedding_filter.py echte
Rohtext-zu-Rohtext-Aehnlichkeit berechnen, statt der vorherigen Naeherung
"alte Zusammenfassung vs. neuer Rohtext".

Kosten dieser Erweiterung, bewusst in Kauf genommen: Snapshot-Dateien
werden deutlich groesser (volle Dateitexte statt 2-3 Satz-Zusammen-
fassungen). Bei den bisher beobachteten Vault-Dateigroessen (einzelne
Markdown-Dateien, keine grossen Assets) bleibt das unproblematisch --
falls das Vault kuenftig sehr grosse Dateien enthaelt, waere eine
Kompression oder ein externer Rohtext-Cache (statt Inline-JSON) ein
moeglicher spaeterer Ausbau, aktuell nicht noetig.

Bewusste Design-Entscheidungen (unveraendert seit 2026-08-23):
- Alle Snapshots werden dauerhaft aufbewahrt, keine automatische Loeschung.
- "Vorheriger Snapshot" = immer der zuletzt gespeicherte Lauf.
- Curator wird aktuell rein MANUELL angestossen.

Speicherort (unveraendert):
    Agentic_System/data/curator_snapshots/<projekt-name>/
        concept_summary_<UTC-Zeitstempel>.json
        latest.json
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


def _read_raw_texts(source_file_mtimes: dict[str, float]) -> dict[str, str]:
    """Liest den aktuellen Rohtext jeder Datei aus source_file_mtimes ein.
    Dateien, die nicht gelesen werden koennen (z.B. geloescht zwischen Scan
    und Speichern), werden mit einer Fehler-Markierung statt einer Exception
    aufgenommen -- ein einzelner Lesefehler soll das gesamte Speichern nicht
    verhindern."""
    raw_texts: dict[str, str] = {}
    for full_path in source_file_mtimes:
        filename = Path(full_path).name
        try:
            raw_texts[filename] = Path(full_path).read_text(encoding="utf-8")
        except OSError as exc:
            raw_texts[filename] = f"__READ_ERROR__: {exc}"
    return raw_texts


def _concept_summary_to_dict(summary: ConceptSummary, raw_texts: dict[str, str]) -> dict:
    return {
        "project_name": summary.project_name,
        "concept_text": summary.concept_text,
        "document_summaries": [asdict(doc) for doc in summary.document_summaries],
        "generated_at": summary.generated_at,
        "source_file_mtimes": summary.source_file_mtimes,
        "raw_text_by_filename": raw_texts,
    }


def _concept_summary_from_dict(data: dict) -> tuple[ConceptSummary, dict[str, str]]:
    document_summaries = [
        DocumentSummary(path=item["path"], summary=item["summary"])
        for item in data["document_summaries"]
    ]
    summary = ConceptSummary(
        project_name=data["project_name"],
        concept_text=data["concept_text"],
        document_summaries=document_summaries,
        generated_at=data["generated_at"],
        source_file_mtimes=data["source_file_mtimes"],
    )
    raw_texts = data.get("raw_text_by_filename", {})
    return summary, raw_texts


def save_snapshot(
    curator_data_root: Path,
    project_name: str,
    summary: ConceptSummary,
) -> Path:
    """Speichert den aktuellen ConceptSummary-Stand INKLUSIVE der aktuellen
    Rohtexte aller Vault-Dateien (siehe Modul-Docstring, NEU seit 2026-08-24).
    Ueberschreibt NIEMALS vorherige zeitgestempelte Snapshots -- nur
    latest.json wird jedes Mal ersetzt."""
    target_dir = _snapshots_dir(curator_data_root, project_name)
    target_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    snapshot_path = target_dir / f"concept_summary_{timestamp}.json"
    latest_path = target_dir / "latest.json"

    raw_texts = _read_raw_texts(summary.source_file_mtimes)
    payload = json.dumps(
        _concept_summary_to_dict(summary, raw_texts), indent=2, ensure_ascii=False
    )

    snapshot_path.write_text(payload, encoding="utf-8")
    latest_path.write_text(payload, encoding="utf-8")

    return snapshot_path


def load_latest_snapshot(
    curator_data_root: Path,
    project_name: str,
) -> ConceptSummary | None:
    """Laedt NUR das ConceptSummary-Objekt aus latest.json (ohne Rohtexte --
    fuer Aufrufer, die die alte API-Signatur erwarten). Fuer Zugriff auf
    die gespeicherten Rohtexte siehe load_latest_snapshot_with_raw_texts()."""
    result = load_latest_snapshot_with_raw_texts(curator_data_root, project_name)
    if result is None:
        return None
    summary, _raw_texts = result
    return summary


def load_latest_snapshot_with_raw_texts(
    curator_data_root: Path,
    project_name: str,
) -> tuple[ConceptSummary, dict[str, str]] | None:
    """Laedt den zuletzt gespeicherten Snapshot INKLUSIVE der zu diesem
    Zeitpunkt gespeicherten Rohtexte. Gibt None zurueck, wenn noch nie ein
    Snapshot fuer dieses Projekt gespeichert wurde."""
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
    sortiert von aeltestem zu neuestem."""
    target_dir = _snapshots_dir(curator_data_root, project_name)
    if not target_dir.exists():
        return []
    return sorted(target_dir.glob("concept_summary_*.json"))
