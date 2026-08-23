"""
agents/curator_agent/embedding_filter.py

Schicht 2 der Evaluator-Kaskade (siehe Chat-Verlauf 2026-08-23, Recherche
zu mehrstufigen LLM-Eval-Pipelines). Zweck: aus den DriftCandidate-
Objekten aus Schicht 1 (drift_diff.py) diejenigen aussortieren, die sich
nur in der FORMULIERUNG unterscheiden (Ollama-Varianz), aber inhaltlich
dieselbe Aussage treffen -- OHNE einen teuren Ollama-Aufruf zu brauchen.

Methode: lokale Sentence-Embeddings (sentence-transformers,
Modell all-MiniLM-L6-v2, ca. 90 MB, einmaliger Download, danach komplett
lokal/offline) + Cosinus-Aehnlichkeit. Schwellwerte nach Recherche-Vorbild
(siehe Chat-Verlauf 2026-08-23):
    >= 0.85  -> keine relevante Aenderung, wird NICHT weitergereicht
    <  0.70  -> deutliche Aenderung, wird weitergereicht
    dazwischen (Grenzfall) -> bewusst TROTZDEM weitergereicht (lieber ein
        unnoetiger Ollama-Aufruf in Schicht 3 als ein uebersehener echter
        Drift-Fall)

WICHTIG: Dieses Modul faellt KEIN inhaltliches Urteil ("ist das jetzt
schlimm/richtig/falsch?") -- das bleibt Schicht 3 (evaluator_agent).
Es beantwortet nur: "lohnt es sich ueberhaupt, das an Schicht 3
weiterzugeben?"
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from agents.curator_agent.drift_diff import DriftCandidate

SIMILARITY_LOW_THRESHOLD = 0.70
SIMILARITY_HIGH_THRESHOLD = 0.85
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"


@dataclass(frozen=True)
class EmbeddingFilterResult:
    candidate: DriftCandidate
    similarity: float | None  # None bei neuen Dokumenten (kein previous_summary)
    passed: bool
    reason: str


@lru_cache(maxsize=1)
def _load_model():
    """Laedt das Embedding-Modell einmalig pro Prozess (lru_cache) --
    Laden dauert ein paar Sekunden, soll nicht pro Kandidat wiederholt
    werden. Import bewusst innerhalb der Funktion, damit ein Fehlen der
    Abhaengigkeit erst beim tatsaechlichen Gebrauch auffaellt, nicht schon
    beim blossen Importieren dieses Moduls (z.B. fuer Tests, die diese
    Funktion mocken wollen)."""
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def _cosine_similarity(a, b) -> float:
    import numpy as np

    a_norm = a / np.linalg.norm(a)
    b_norm = b / np.linalg.norm(b)
    return float(np.dot(a_norm, b_norm))


def filter_candidates(candidates: list[DriftCandidate]) -> list[EmbeddingFilterResult]:
    """Bewertet jeden Kandidaten aus Schicht 1. Neue Dokumente (previous_summary
    ist None) werden IMMER durchgelassen -- fuer sie gibt es nichts zu
    vergleichen, und ein neues Dokument ist per Definition relevant genug,
    um wenigstens einmal inhaltlich geprueft zu werden."""
    results: list[EmbeddingFilterResult] = []

    candidates_needing_embedding = [c for c in candidates if c.previous_summary is not None]

    if candidates_needing_embedding:
        model = _load_model()
        texts_previous = [c.previous_summary for c in candidates_needing_embedding]
        texts_current = [c.current_summary for c in candidates_needing_embedding]
        embeddings_previous = model.encode(texts_previous)
        embeddings_current = model.encode(texts_current)
    else:
        embeddings_previous = []
        embeddings_current = []

    embedding_idx = 0
    for candidate in candidates:
        if candidate.previous_summary is None:
            results.append(
                EmbeddingFilterResult(
                    candidate=candidate,
                    similarity=None,
                    passed=True,
                    reason="Neues Dokument -- kein Vergleich moeglich, wird direkt weitergereicht.",
                )
            )
            continue

        similarity = _cosine_similarity(
            embeddings_previous[embedding_idx], embeddings_current[embedding_idx]
        )
        embedding_idx += 1

        if similarity >= SIMILARITY_HIGH_THRESHOLD:
            passed = False
            reason = (
                f"Aehnlichkeit {similarity:.3f} >= {SIMILARITY_HIGH_THRESHOLD} -- "
                f"vermutlich nur Formulierungsvarianz, kein echter Inhaltswechsel."
            )
        elif similarity < SIMILARITY_LOW_THRESHOLD:
            passed = True
            reason = (
                f"Aehnlichkeit {similarity:.3f} < {SIMILARITY_LOW_THRESHOLD} -- "
                f"deutliche inhaltliche Aenderung, wird weitergereicht."
            )
        else:
            passed = True
            reason = (
                f"Aehnlichkeit {similarity:.3f} im Graubereich "
                f"({SIMILARITY_LOW_THRESHOLD}-{SIMILARITY_HIGH_THRESHOLD}) -- "
                f"sicherheitshalber weitergereicht."
            )

        results.append(
            EmbeddingFilterResult(
                candidate=candidate, similarity=similarity, passed=passed, reason=reason
            )
        )

    return results
