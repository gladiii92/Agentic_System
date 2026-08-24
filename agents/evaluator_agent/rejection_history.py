"""
agents/evaluator_agent/rejection_history.py

Speichert vom Nutzer ABGELEHNTE Vorschlaege strukturiert ab, damit sie
kuenftigen Prompts als Few-Shot-Negativbeispiele mitgegeben werden koennen
(siehe Chat-Verlauf 2026-08-24 -- BEWUSST kein Modell-Finetuning, siehe
proposal_writer_prompt.py-Docstring fuer die Begruendung).

Architekturprinzip (siehe Chat-Verlauf): dieses Modul ist bewusst
GENERISCH gehalten (nicht curator-spezifisch) -- agent_name wird als
Parameter mitgegeben, damit spaeter auch der Builder-Agent dieselbe
Infrastruktur fuer seine eigenen Ablehnungen nutzen kann, nur mit
agent_name="builder_agent" statt "curator_agent".

Speicherort:
    Agentic_System/data/rejection_history/<agent_name>.jsonl

Format: JSON Lines (eine Ablehnung pro Zeile) -- bewusst append-only,
analog zum "kein hartes Delete"-Prinzip aus AI_Project_Reviewer
(findings_store.py, dismiss statt delete).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class RejectedProposal:
    agent_name: str
    filename: str
    contradiction_summary: str
    suggested_update: str
    proposed_text_excerpt: str  # nur ein Ausschnitt, nicht der volle Text -- Datei klein halten
    rejection_reason: str
    rejected_at: str


def _history_path(rejection_history_root: Path, agent_name: str) -> Path:
    return rejection_history_root / f"{agent_name}.jsonl"


def record_rejection(
    rejection_history_root: Path,
    agent_name: str,
    filename: str,
    contradiction_summary: str,
    suggested_update: str,
    proposed_text: str,
    rejection_reason: str,
) -> None:
    """Haengt eine neue Ablehnung ans Ende der JSONL-Datei an. rejection_reason
    ist PFLICHT (analog zu findings dismiss --reason in AI_Project_Reviewer,
    Dokumentationszwang-Prinzip) -- der Aufrufer (run_drift_check.py) muss
    den Nutzer explizit danach fragen, bevor diese Funktion aufgerufen wird."""
    path = _history_path(rejection_history_root, agent_name)
    path.parent.mkdir(parents=True, exist_ok=True)

    entry = RejectedProposal(
        agent_name=agent_name,
        filename=filename,
        contradiction_summary=contradiction_summary,
        suggested_update=suggested_update,
        proposed_text_excerpt=proposed_text[:500],
        rejection_reason=rejection_reason,
        rejected_at=datetime.now(timezone.utc).isoformat(),
    )

    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(asdict(entry), ensure_ascii=False) + "\n")


def load_rejections(rejection_history_root: Path, agent_name: str) -> list[RejectedProposal]:
    """Laedt alle bisherigen Ablehnungen fuer diesen Agenten. Gibt leere
    Liste zurueck, wenn noch nie eine Ablehnung aufgetreten ist."""
    path = _history_path(rejection_history_root, agent_name)
    if not path.exists():
        return []

    rejections = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        data = json.loads(line)
        rejections.append(RejectedProposal(**data))
    return rejections


def format_for_prompt(rejections: list[RejectedProposal], max_examples: int = 5) -> list[str]:
    """Formatiert die JUENGSTEN max_examples Ablehnungen als fertige Few-
    Shot-Text-Bloecke fuer proposal_writer_prompt.py. Bewusst nur die
    neuesten, nicht alle -- verhindert, dass der Prompt bei wachsender
    Historie unbegrenzt laenger wird (TODO fuer spaeter: relevanteste statt
    nur neueste auswaehlen, z.B. per Embedding-Aehnlichkeit zum aktuellen
    Fall -- kein Blocker fuer Phase 1)."""
    recent = rejections[-max_examples:]
    blocks = []
    for r in recent:
        blocks.append(
            f"- Datei: {r.filename}\n"
            f"  Abgelehnter Vorschlag: {r.suggested_update}\n"
            f"  Grund der Ablehnung: {r.rejection_reason}"
        )
    return blocks
