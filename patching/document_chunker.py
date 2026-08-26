"""
patching/document_chunker.py

NEUES Modul (2026-08-26, Full-Audit-Feature -- siehe Chat-Verlauf).

Teilt einen Dokumenttext in Zeilen-basierte Chunks fuer den separaten
"Full Audit"-Modus (run_full_audit.py). Bewusst NICHT nach Markdown-
Headern (##) gegliedert -- das wuerde nur fuer Markdown-Dokumente mit
konsistenter Ueberschriftenstruktur funktionieren, aber das System soll
generisch fuer beliebige Textdateien nutzbar sein (siehe Chat-Verlauf:
"nicht in jedem Dokument gibt es ##-Header").

Jeder Chunk bekommt zusaetzlich ein paar Ueberlappungszeilen vom
vorherigen/naechsten Chunk (OVERLAP_LINES), damit ein Satz, der genau an
einer Chunk-Grenze auseinandergerissen wird, trotzdem in mindestens
einem Chunk vollstaendig sichtbar ist. Das mitgelieferte volle
Dokument (siehe drift_judge_prompt.py full_document_text-Feld) dient
zusaetzlich als Referenz fuer Widersprueche ueber Chunk-Grenzen hinweg.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_CHUNK_LINES = 200
DEFAULT_OVERLAP_LINES = 10


@dataclass(frozen=True)
class DocumentChunk:
    chunk_index: int
    start_line: int  # 1-basiert, inklusive
    end_line: int  # 1-basiert, inklusive
    text: str


def compute_document_chunks(
    full_text: str,
    chunk_lines: int = DEFAULT_CHUNK_LINES,
    overlap_lines: int = DEFAULT_OVERLAP_LINES,
) -> list[DocumentChunk]:
    """Teilt full_text in aufeinanderfolgende Zeilenbloecke. Bei
    Dokumenten, die kuerzer als chunk_lines sind, wird genau EIN Chunk
    mit dem kompletten Text zurueckgegeben."""
    lines = full_text.splitlines()
    total_lines = len(lines)

    if total_lines == 0:
        return []

    if total_lines <= chunk_lines:
        return [DocumentChunk(chunk_index=0, start_line=1, end_line=total_lines, text=full_text)]

    chunks: list[DocumentChunk] = []
    chunk_index = 0
    line_pointer = 0

    while line_pointer < total_lines:
        raw_start = line_pointer
        raw_end = min(line_pointer + chunk_lines, total_lines)

        context_start = max(0, raw_start - overlap_lines)
        context_end = min(total_lines, raw_end + overlap_lines)

        chunk_text = "\n".join(lines[context_start:context_end])

        chunks.append(
            DocumentChunk(
                chunk_index=chunk_index,
                start_line=context_start + 1,
                end_line=context_end,
                text=chunk_text,
            )
        )

        chunk_index += 1
        line_pointer = raw_end

    return chunks


def render_chunk_for_prompt(chunk: DocumentChunk) -> str:
    """Rendert einen Chunk als Text fuer den Judge-Prompt -- ohne
    -/+ Diff-Praefixe (das ist kein echter Hunk, sondern ein reiner
    Textausschnitt, der komplett auf Widersprueche geprueft wird)."""
    return f"[Zeilen {chunk.start_line}-{chunk.end_line} des Dokuments]\n{chunk.text}"
