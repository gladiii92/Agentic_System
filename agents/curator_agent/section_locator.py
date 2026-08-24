"""
agents/curator_agent/section_locator.py

VERSION 2 (2026-08-24, Fix 6 -- robustere Abschnitts-Lokalisierung nach
realem Fehlerfall, siehe Chat-Verlauf): Version 1 nutzte reine Wort-
ueberlappung zwischen Judge-Begruendung und Abschnittstext -- das waehlte
in einem echten Testlauf den FALSCHEN Abschnitt ("MVP-Definition" statt
der eigentlichen Phasen-Tabelle), weil beide Abschnitte aehnliche
thematische Woerter (Ruff, Bandit, Ollama) enthalten.

FIX 1 -- Status-Keyword-Bonus: Abschnitte, die Status-Schluesselwoerter
("Abgeschlossen", "Offen", "Status:", Tabellen-Pipe-Zeichen "|") enthalten,
bekommen einen Bonus -- Drift-Faelle drehen sich fast immer um FALSCHE
STATUSANGABEN, also sind Abschnitte mit Status-Tabellen die wahrschein-
licheren Ziele als reine Beschreibungstexte.

FIX 2 -- Trennlinien-Erhaltung beim Zusammenfuegen: replace_section()
stellt jetzt sicher, dass zwischen dem neuen Abschnittstext und dem
nachfolgenden Text mindestens die im Original vorhandene Anzahl
Zeilenumbrueche erhalten bleibt (verhindert das beobachtete Verschmelzen
von "## MVP-Definition" und "## Phase 1" durch fehlende Leerzeile/---).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

SECTION_HEADING_PATTERN = re.compile(r"^## .+$", re.MULTILINE)
STATUS_KEYWORDS = ["abgeschlossen", "offen", "status:", "nächster schritt"]
STATUS_BONUS_WEIGHT = 0.5  # zusaetzlicher Score-Anteil pro erkanntem Status-Keyword-Treffer


@dataclass(frozen=True)
class DocumentSection:
    heading: str
    start_index: int
    end_index: int  # exklusiv
    text: str


def split_into_sections(full_text: str) -> list[DocumentSection]:
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
    words_a = {w.lower() for w in re.findall(r"\w{4,}", text_a)}
    words_b = {w.lower() for w in re.findall(r"\w{4,}", text_b)}

    if not words_a:
        return 0.0

    overlap = words_a & words_b
    return len(overlap) / len(words_a)


def _status_keyword_bonus(section_text: str, query: str) -> float:
    """Bonus NUR, wenn sowohl der Abschnitt ALS AUCH die Judge-Begruendung
    (query) Status-Sprache verwenden -- verhindert, dass EIN generischer
    Abschnitt allein durch eigene Status-Woerter bevorzugt wird, ohne dass
    die Anfrage selbst nach Status fragt."""
    query_lower = query.lower()
    section_lower = section_text.lower()

    query_mentions_status = any(kw in query_lower for kw in STATUS_KEYWORDS)
    if not query_mentions_status:
        return 0.0

    matches = sum(1 for kw in STATUS_KEYWORDS if kw in section_lower)
    pipe_bonus = 0.3 if "|" in section_text else 0.0  # Tabellen-Indikator
    return min(matches * STATUS_BONUS_WEIGHT + pipe_bonus, 1.5)


def find_most_relevant_section(
    sections: list[DocumentSection],
    contradiction_summary: str,
    suggested_update: str,
) -> DocumentSection:
    """Kombiniert Wortueberlappung MIT Status-Keyword-Bonus (siehe Fix 1
    oben). Bei Gleichstand wird der ERSTE Treffer gewaehlt."""
    query = f"{contradiction_summary} {suggested_update}"

    best_section = sections[0]
    best_score = -1.0

    for section in sections:
        if not section.heading:
            continue
        overlap_score = _word_overlap_score(query, section.text)
        bonus = _status_keyword_bonus(section.text, query)
        total_score = overlap_score + bonus

        if total_score > best_score:
            best_score = total_score
            best_section = section

    return best_section


def replace_section(full_text: str, section: DocumentSection, new_section_text: str) -> str:
    """Setzt den Volltext programmatisch neu zusammen. FIX 2 (siehe Modul-
    Docstring): stellt sicher, dass die Anzahl der Zeilenumbrueche am Ende
    von new_section_text mindestens der im Original entspricht, bevor der
    nachfolgende Text angehaengt wird -- verhindert das Verschmelzen von
    Abschnitten durch fehlende Leerzeilen/Trennlinien."""
    original_trailing_newlines = len(section.text) - len(section.text.rstrip("\n"))
    new_trailing_newlines = len(new_section_text) - len(new_section_text.rstrip("\n"))

    if new_trailing_newlines < original_trailing_newlines:
        new_section_text = new_section_text.rstrip("\n") + "\n" * original_trailing_newlines

    return full_text[: section.start_index] + new_section_text + full_text[section.end_index :]
