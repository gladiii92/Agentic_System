"""
agents/curator_agent/section_locator.py

Zerlegt ein Markdown-Dokument in Abschnitte (getrennt durch "## "-
Ueberschriften der obersten Ebene, analog zur beobachteten Struktur von
ROADMAP.md: "## Phase X - ...") und identifiziert, welcher Abschnitt am
ehesten zur festgestellten Diskrepanz passt.

WARUM DIESER BAUSTEIN NEU IST (siehe Chat-Verlauf 2026-08-24): Der erste
echte Testlauf des proposal_writer-Moduls zeigte, dass ein "gib die ganze
Datei neu aus"-Ansatz bei laengeren Dokumenten unzuverlaessig ist --
Ollama ersetzte mehrere unbeteiligte Phasen-Abschnitte durch identischen
Platzhaltertext und leckte den eigenen Prompt ins Ergebnis. Die robuste
Loesung: NUR den tatsaechlich betroffenen Abschnitt an Ollama schicken,
den Rest der Datei PROGRAMMATISCH (nicht durchs Modell) unveraendert
zusammenfuegen -- das macht eine Beschaedigung anderer Abschnitte
STRUKTURELL unmoeglich, unabhaengig davon, was das Modell tut.

Bewusst einfache Heuristik (TF-IDF-artiger Wortueberlappungs-Score
zwischen contradiction_summary und jedem Abschnittstext) statt Embedding
-- fuer diese Lokalisierungsaufgabe reicht ein einfacher, deterministischer
Score, kein weiteres ML-Modell noetig (Prinzip: einfachste ausreichende
Loesung zuerst, siehe Kaskaden-Philosophie aus embedding_filter.py).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SECTION_HEADING_PATTERN = re.compile(r"^## .+$", re.MULTILINE)


@dataclass(frozen=True)
class DocumentSection:
    heading: str
    start_index: int
    end_index: int  # exklusiv
    text: str


def split_into_sections(full_text: str) -> list[DocumentSection]:
    """Teilt den Text an jeder Zeile, die mit '## ' beginnt. Text VOR der
    ersten Ueberschrift wird als eigener Abschnitt mit heading='' behandelt
    (z.B. Titel/Intro-Text vor der ersten Phase in ROADMAP.md)."""
    matches = list(SECTION_HEADING_PATTERN.finditer(full_text))

    if not matches:
        return [DocumentSection(heading="", start_index=0, end_index=len(full_text), text=full_text)]

    sections = []

    if matches[0].start() > 0:
        sections.append(
            DocumentSection(heading="", start_index=0, end_index=matches[0].start(), text=full_text[: matches[0].start()])
        )

    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(full_text)
        sections.append(
            DocumentSection(heading=match.group().strip(), start_index=start, end_index=end, text=full_text[start:end])
        )

    return sections


def _word_overlap_score(text_a: str, text_b: str) -> float:
    """Einfacher, deterministischer Ueberlappungs-Score: Anteil der Woerter
    aus text_a, die auch in text_b vorkommen (case-insensitiv, nur Woerter
    ab 4 Zeichen, um Fuellwoerter zu ignorieren)."""
    words_a = {w.lower() for w in re.findall(r"\w{4,}", text_a)}
    words_b = {w.lower() for w in re.findall(r"\w{4,}", text_b)}

    if not words_a:
        return 0.0

    overlap = words_a & words_b
    return len(overlap) / len(words_a)


def find_most_relevant_section(
    sections: list[DocumentSection],
    contradiction_summary: str,
    suggested_update: str,
) -> DocumentSection:
    """Findet den Abschnitt mit der hoechsten Wortueberlappung zum
    kombinierten Text aus contradiction_summary + suggested_update. Bei
    Gleichstand wird der ERSTE Treffer gewaehlt (deterministisch,
    reproduzierbar)."""
    query = f"{contradiction_summary} {suggested_update}"

    best_section = sections[0]
    best_score = -1.0

    for section in sections:
        if not section.heading:
            continue  # Intro-Text vor der ersten Ueberschrift wird nie als Ziel gewaehlt
        score = _word_overlap_score(query, section.text)
        if score > best_score:
            best_score = score
            best_section = section

    return best_section


def replace_section(full_text: str, section: DocumentSection, new_section_text: str) -> str:
    """Setzt den Volltext programmatisch neu zusammen: alles vor/nach dem
    Zielabschnitt bleibt BYTE-IDENTISCH zum Original, nur der Zielabschnitt
    wird ersetzt. Das ist die eigentliche Sicherheitsgarantie dieses Moduls."""
    return full_text[: section.start_index] + new_section_text + full_text[section.end_index :]
