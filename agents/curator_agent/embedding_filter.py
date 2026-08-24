"""
agents/curator_agent/embedding_filter.py

Schicht 2 der Evaluator-Kaskade, finale Version (2026-08-24). Zweck: aus
den DriftCandidate-Objekten aus Schicht 1 (drift_diff.py) diejenigen
aussortieren, die sich nur in der FORMULIERUNG unterscheiden, aber
inhaltlich dieselbe Aussage treffen -- OHNE einen teuren Ollama-Aufruf.

ENTWICKLUNGSGESCHICHTE (siehe Chat-Verlauf 2026-08-23/24, wichtig fuer
kuenftige Aenderungen):
1. Erste Version verglich Ollama-ZUSAMMENFASSUNGEN (alt vs. neu). Realer
   Test zeigte: ROADMAP.md mit echter inhaltlicher Aenderung wurde trotzdem
   mit Aehnlichkeit 0.928 faelschlich verworfen -- Zusammenfassungen sind
   ein verlustbehafteter Filter, relevante Nuancen gehen darin oft verloren.
2. Zweite Version verglich ALTE Zusammenfassung vs. NEUER Rohtext (Notloesung,
   weil zu diesem Zeitpunkt noch keine Rohtext-Historie existierte).
3. DIESE Version (final fuer Phase 1): vergleicht ECHTEN Rohtext vs. ECHTEN
   Rohtext, basierend auf der in snapshot_store.py NEU eingefuehrten
   raw_text_by_filename-Historie. Das ist der technisch korrekte Vergleich.

Zusaetzlich (auf Nutzerwunsch, siehe Chat-Verlauf 2026-08-24): dieses Modul
berechnet PARALLEL weiterhin die reine Summary-zu-Summary-Aehnlichkeit als
Beobachtungsgroesse (summary_similarity) -- damit ueber mehrere echte
Laeufe hinweg sichtbar bleibt, wie stark sich beide Ansaetze unterscheiden,
falls das kuenftig noch einmal relevant wird.

Methode: lokale Sentence-Embeddings (sentence-transformers,
all-MiniLM-L6-v2) + Cosinus-Aehnlichkeit, komplett offline nach dem
einmaligen Modell-Download.

Schwellwerte (siehe TODO -- noch nicht ueber mehrere echte Faelle kalibriert):
    >= 0.85  -> keine relevante Aenderung, wird NICHT weitergereicht
    <  0.70  -> deutliche Aenderung, wird weitergereicht
    dazwischen -> Grenzfall, wird sicherheitshalber weitergereicht
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from agents.curator_agent.drift_diff import DriftCandidate

SIMILARITY_LOW_THRESHOLD = 0.70
SIMILARITY_HIGH_THRESHOLD = 0.85
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

# TODO (Kalibrierung, kein Blocker fuer Phase 1): nach mehreren echten
# Laeufen mit bekanntermassen echtem vs. bekanntermassen falschem Drift
# pruefen, ob diese Schwellwerte fuer ROHTEXT-Vergleiche optimal sind.


class EmbeddingComparisonError(Exception):
    """Fehler beim Aufbau der Vergleichsdaten (z.B. fehlender Rohtext im
    alten Snapshot)."""


@dataclass(frozen=True)
class EmbeddingFilterResult:
    candidate: DriftCandidate
    raw_text_similarity: float | None  # PRIMAERE Entscheidungsgrundlage
    summary_similarity: float | None  # NUR Beobachtung/Vergleich (siehe Docstring)
    passed: bool
    reason: str


@lru_cache(maxsize=1)
def _load_model():
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def _cosine_similarity(a, b) -> float:
    import numpy as np

    a_norm = a / np.linalg.norm(a)
    b_norm = b / np.linalg.norm(b)
    return float(np.dot(a_norm, b_norm))


def filter_candidates(
    candidates: list[DriftCandidate],
    previous_raw_texts: dict[str, str],
    current_raw_texts: dict[str, str],
) -> list[EmbeddingFilterResult]:
    """Bewertet jeden Kandidaten aus Schicht 1.

    Args:
        candidates: Ergebnis aus drift_diff.diff_concept_summaries().
        previous_raw_texts: raw_text_by_filename aus dem VORHERIGEN
            Snapshot (siehe snapshot_store.load_latest_snapshot_with_raw_texts).
        current_raw_texts: Rohtexte des AKTUELLEN Laufs, frisch gelesen
            (siehe run_drift_check.py -- werden dort ueber
            source_file_mtimes der aktuellen ConceptSummary eingelesen).

    Neue Dokumente (previous_summary des Kandidaten ist None) werden IMMER
    durchgelassen -- fuer sie gibt es nichts zu vergleichen.
    """
    results: list[EmbeddingFilterResult] = []

    new_document_candidates = [c for c in candidates if c.previous_summary is None]
    comparable_candidates = [c for c in candidates if c.previous_summary is not None]

    for candidate in new_document_candidates:
        results.append(
            EmbeddingFilterResult(
                candidate=candidate,
                raw_text_similarity=None,
                summary_similarity=None,
                passed=True,
                reason="Neues Dokument -- kein Vergleich moeglich, wird direkt weitergereicht.",
            )
        )

    if not comparable_candidates:
        return results

    model = _load_model()

    raw_previous, raw_current, missing = [], [], []
    for candidate in comparable_candidates:
        prev_text = previous_raw_texts.get(candidate.filename)
        curr_text = current_raw_texts.get(candidate.filename)
        if prev_text is None or curr_text is None:
            missing.append(candidate.filename)
            prev_text = prev_text or candidate.previous_summary
            curr_text = curr_text or candidate.current_summary
        raw_previous.append(prev_text)
        raw_current.append(curr_text)

    if missing:
        print(
            f"    WARNUNG: Fuer folgende Dateien fehlt Rohtext-Historie, "
            f"falle auf Summary-Vergleich zurueck: {missing}"
        )

    embeddings_raw_previous = model.encode(raw_previous)
    embeddings_raw_current = model.encode(raw_current)

    summary_previous = [c.previous_summary for c in comparable_candidates]
    summary_current = [c.current_summary for c in comparable_candidates]
    embeddings_summary_previous = model.encode(summary_previous)
    embeddings_summary_current = model.encode(summary_current)

    for i, candidate in enumerate(comparable_candidates):
        raw_similarity = _cosine_similarity(embeddings_raw_previous[i], embeddings_raw_current[i])
        summary_similarity = _cosine_similarity(
            embeddings_summary_previous[i], embeddings_summary_current[i]
        )

        if raw_similarity >= SIMILARITY_HIGH_THRESHOLD:
            passed = False
            reason = (
                f"Rohtext-Aehnlichkeit {raw_similarity:.3f} >= {SIMILARITY_HIGH_THRESHOLD} -- "
                f"keine relevante inhaltliche Aenderung. "
                f"(Zum Vergleich, Summary-only waere gewesen: {summary_similarity:.3f})"
            )
        elif raw_similarity < SIMILARITY_LOW_THRESHOLD:
            passed = True
            reason = (
                f"Rohtext-Aehnlichkeit {raw_similarity:.3f} < {SIMILARITY_LOW_THRESHOLD} -- "
                f"deutliche inhaltliche Aenderung. "
                f"(Zum Vergleich, Summary-only waere gewesen: {summary_similarity:.3f})"
            )
        else:
            passed = True
            reason = (
                f"Rohtext-Aehnlichkeit {raw_similarity:.3f} im Graubereich -- "
                f"sicherheitshalber weitergereicht. "
                f"(Zum Vergleich, Summary-only waere gewesen: {summary_similarity:.3f})"
            )

        results.append(
            EmbeddingFilterResult(
                candidate=candidate,
                raw_text_similarity=raw_similarity,
                summary_similarity=summary_similarity,
                passed=passed,
                reason=reason,
            )
        )

    return results
