"""
agents/curator_agent/embedding_filter.py

Schicht 2 der Evaluator-Kaskade, finale Version (2026-08-24, Fix 3 --
Chunking). Zweck: aus den DriftCandidate-Objekten aus Schicht 1
(drift_diff.py) diejenigen aussortieren, die sich nur in der FORMULIERUNG
unterscheiden, aber inhaltlich dieselbe Aussage treffen -- OHNE einen
teuren Ollama-Aufruf.

KRITISCHER BUG GEFUNDEN UND BEHOBEN AM 2026-08-24 (siehe Chat-Verlauf,
unbedingt lesen vor kuenftigen Aenderungen an diesem Modul):
Das Modell all-MiniLM-L6-v2 hat ein HARTES Token-Limit von 256 Tokens
(siehe model.max_seq_length). Laengere Texte werden beim Encodieren
STILLSCHWEIGEND abgeschnitten -- KEIN Fehler, KEINE Warnung im normalen
Aufruf (nur eine leise Transformers-Warnung im Log, die leicht uebersehen
wird). Realer Beleg: ROADMAP.md (7813 Zeichen, 3002 Tokens) wurde nur zu
den ERSTEN 256 Tokens (~8.5% des Textes) embedded -- eine inhaltliche
Aenderung WEITER HINTEN im Dokument (z.B. eine ergaenzte Tabellenzeile)
wurde vom Modell nie "gesehen", weshalb die Aehnlichkeit faelschlich bei
1.000 lag, obwohl sich der Text nachweislich geaendert hatte.

FIX: Texte werden jetzt in ueberlappende Chunks aufgeteilt (siehe
CHUNK_SIZE_CHARS/CHUNK_OVERLAP_CHARS unten), jeder Chunk einzeln embedded,
und die finale Aehnlichkeit wird ueber ALLE Chunk-Paar-Kombinationen als
MINIMUM aggregiert (nicht Durchschnitt!) -- Begruendung: wenn IRGENDEIN
Chunk-Paar eine niedrige Aehnlichkeit zeigt, gibt es dort eine relevante
Aenderung, die nicht durch andere, unveraenderte Chunks "verwaschen"
werden darf. Ein Durchschnitt wuerde genau das Problem von vorhin auf
andere Weise reproduzieren (viele unveraenderte Chunks verduennen den
einen relevanten Unterschied).

Methode weiterhin: lokale Sentence-Embeddings (sentence-transformers,
all-MiniLM-L6-v2) + Cosinus-Aehnlichkeit, komplett offline nach dem
einmaligen Modell-Download.

Schwellwerte (unveraendert, jetzt aber auf Chunk-Ebene angewendet):
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

# Chunk-Groesse bewusst deutlich UNTER dem Token-Limit (256 Tokens) gewaehlt.
# 800 Zeichen entsprechen bei natuerlicher deutscher/englischer Prosa grob
# 150-220 Tokens -- Sicherheitsabstand zum harten 256-Token-Limit, falls
# ein Chunk zufaellig an einer Stelle mit ungewoehnlich vielen kurzen
# Tokens (z.B. Tabellen mit vielen Pipe-Zeichen) landet.
CHUNK_SIZE_CHARS = 800
CHUNK_OVERLAP_CHARS = 200  # verhindert, dass eine Aenderung genau an einer Chunk-Grenze "zerschnitten" und dadurch verwaesserst wird


@dataclass(frozen=True)
class EmbeddingFilterResult:
    candidate: DriftCandidate
    raw_text_similarity: float | None  # PRIMAERE Entscheidungsgrundlage (Minimum ueber alle Chunk-Paare)
    summary_similarity: float | None  # NUR Beobachtung/Vergleich
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


def _chunk_text(text: str, chunk_size: int = CHUNK_SIZE_CHARS, overlap: int = CHUNK_OVERLAP_CHARS) -> list[str]:
    """Teilt einen Text in ueberlappende Zeichen-Chunks. Bewusst zeichen-
    basiert statt satzbasiert -- einfacher, robuster gegen unterschiedliche
    Formatierungen (Tabellen, Listen, etc. in Markdown-Vault-Dateien), und
    fuer unseren Zweck (Aehnlichkeits-Screening, nicht Praesentation)
    ausreichend genau."""
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks


def _min_pairwise_similarity(chunks_a: list[str], chunks_b: list[str], model) -> float:
    """Berechnet die Aehnlichkeit zwischen zwei Chunk-Listen als das
    MINIMUM ueber alle paarweisen Kombinationen (siehe Modul-Docstring fuer
    die Begruendung, warum Minimum statt Durchschnitt). Bei sehr vielen
    Chunks (lange Dokumente) waechst dieser Vergleich quadratisch -- fuer
    die bisher beobachteten Vault-Dateigroessen (wenige tausend Zeichen)
    unproblematisch; bei deutlich groesseren Dokumenten waere eine
    guenstigere Heuristik (z.B. nur gleich positionierte Chunks vergleichen)
    ein moeglicher spaeterer Ausbau."""
    if not chunks_a or not chunks_b:
        return 1.0  # beide leer -- kein Unterschied feststellbar, konservativ als "unveraendert" werten

    embeddings_a = model.encode(chunks_a)
    embeddings_b = model.encode(chunks_b)

    similarities = [
        _cosine_similarity(emb_a, emb_b) for emb_a in embeddings_a for emb_b in embeddings_b
    ]
    return min(similarities)


def filter_candidates(
    candidates: list[DriftCandidate],
    previous_raw_texts: dict[str, str],
    current_raw_texts: dict[str, str],
) -> list[EmbeddingFilterResult]:
    """Bewertet jeden Kandidaten aus Schicht 1 mittels Chunk-basiertem
    Rohtext-Vergleich (siehe Modul-Docstring, Fix vom 2026-08-24).

    Args:
        candidates: Ergebnis aus drift_diff.diff_concept_summaries().
        previous_raw_texts: raw_text_by_filename aus dem VORHERIGEN Snapshot.
        current_raw_texts: Rohtexte des AKTUELLEN Laufs.
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

    for candidate in comparable_candidates:
        prev_text = previous_raw_texts.get(candidate.filename)
        curr_text = current_raw_texts.get(candidate.filename)

        used_fallback = prev_text is None or curr_text is None
        if used_fallback:
            print(f"    WARNUNG: Rohtext-Historie fehlt fuer {candidate.filename}, falle auf Summary-Vergleich zurueck.")
            prev_text = prev_text or candidate.previous_summary
            curr_text = curr_text or candidate.current_summary

        prev_chunks = _chunk_text(prev_text)
        curr_chunks = _chunk_text(curr_text)

        raw_similarity = _min_pairwise_similarity(prev_chunks, curr_chunks, model)

        summary_embeddings = model.encode([candidate.previous_summary, candidate.current_summary])
        summary_similarity = _cosine_similarity(summary_embeddings[0], summary_embeddings[1])

        chunk_info = f"({len(prev_chunks)} vs {len(curr_chunks)} Chunks)"

        if raw_similarity >= SIMILARITY_HIGH_THRESHOLD:
            passed = False
            reason = (
                f"Rohtext-Aehnlichkeit (Minimum ueber Chunks) {raw_similarity:.3f} "
                f">= {SIMILARITY_HIGH_THRESHOLD} {chunk_info} -- keine relevante Aenderung. "
                f"(Summary-only waere gewesen: {summary_similarity:.3f})"
            )
        elif raw_similarity < SIMILARITY_LOW_THRESHOLD:
            passed = True
            reason = (
                f"Rohtext-Aehnlichkeit (Minimum ueber Chunks) {raw_similarity:.3f} "
                f"< {SIMILARITY_LOW_THRESHOLD} {chunk_info} -- deutliche Aenderung. "
                f"(Summary-only waere gewesen: {summary_similarity:.3f})"
            )
        else:
            passed = True
            reason = (
                f"Rohtext-Aehnlichkeit (Minimum ueber Chunks) {raw_similarity:.3f} "
                f"im Graubereich {chunk_info} -- sicherheitshalber weitergereicht. "
                f"(Summary-only waere gewesen: {summary_similarity:.3f})"
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
