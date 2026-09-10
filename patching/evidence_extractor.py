"""Extract concise evidence statements (status/facts) from a document chunk.

Dieser Extractor extrahiert ausschliesslich status-tragende Aussagen:
- `Status:`-Zeilen (angereichert mit dem Kontext der aktuellen Phase)
- Zeilen der Gesamtstatus-Tabelle (Markdown)
- Status-Angaben direkt in Phasen-Headern ("Phase 2.5: Abgeschlossen ...")
- Kompakte Freitext-Aussagen mit Status-Schluesselwoertern

Alles andere (Aufzaehlungen, nummerierte Listen, Abschnittsueberschriften,
Dokumentationshinweise, laengere erlaeuternde Saetze) wird gefiltert, damit
der Cross-Chunk-Judge ein sauberes Signal bekommt.
"""

from __future__ import annotations

import re
from typing import List, Optional

from patching.evidence_models import Evidence

# Status-Vokabular (angelehnt an die ROADMAP-Konvention der Zielprojekte).
# "final"/"fertig" bewusst NICHT enthalten: kein offizieller Statuswert und
# erzeugt Rauschen (z.B. "5. review-CLI-Command final in cli.py einfgen").
_STATUS_KEYWORDS = (
    "abgeschlossen",
    "offen",
    "in arbeit",
    "in arbeitung",
    "real verifiziert",
    "nächster schritt",
    "in arbeit (2026-",
    "abgeschlossen (2026-",
)

# Laengere Freitext-Saetze sind keine kompakte Evidence -- sie erklaeren
# eher, als dass sie einen Status festschreiben.
_MAX_KEYWORD_LINE_CHARS = 160

_STATUS_LINE_RE = re.compile(r"(?i)^status\s*[:=]\s*(.+)$")
_TABLE_ROW_RE = re.compile(r"^\|\s*(.+?)\s*\|\s*(.+?)\s*\|\s*$")
_PHASE_HEADER_RE = re.compile(r"^\s*##\s*Phase\s*([\d.]+)\s*[-–—]\s*(.+)$")

# Matcht NUR, wenn nach der Phasennummer tatsaechlich ein Statuswert folgt.
_STATUS_VOCAB_ALT = r"(abgeschlossen\s+und\s+real\s+verifiziert|abgeschlossen|offen|nächster\s+schritt|in\s+arbeit|in\s+arbeitung)"
_PHASE_STATUS_LINE_RE = re.compile(
    r"(?i)^phase\s+[\d.]+\s*[-–—:]\s*(?:status\s*[:=])?\s*"
    + _STATUS_VOCAB_ALT
    + r"\b.*$"
)
# Capture-Gruppen fuer _PHASE_STATUS_LINE_RE: den Statuswert holen.
_PHASE_STATUS_VALUE_RE = re.compile(
    r"(?i)(?:status\s*[:=])?\s*(" + _STATUS_VOCAB_ALT + r")(.*)$"
)

_TABLE_SEPARATOR_RE = re.compile(r"^\|\s*-{3,}\s*(\|\s*-{3,}\s*)*\|\s*$")
_NUMBERED_LIST_RE = re.compile(r"^\s*\d+[.)]\s+")
_SKIP_LINE_PREFIXES = frozenset(("-", "*", ">", "!"))
_SECTION_HEADING_RE = re.compile(r"^##\s+\S")

# Datumsangaben in Klammern (ISO "2026-08-24" oder deutsch "25.08.2026").
# Wird als ISO-String (JJJJ-MM-TT) extrahiert -- Grundlage der
# Datums-Rangfolgen-Regel (die neueste datierte Aussage ist die Wahrheit).
_DATE_ISO_RE = re.compile(r"\(\d{4}-\d{2}-\d{2}\)")
_DATE_DE_RE = re.compile(r"\(\d{2}\.\d{2}\.\d{4}\)")

# Abschnitts-Schluesselwoerter fuer die Kategorie-Zuordnung.
_SECTION_MERKPOSTEN_KEYWORDS = ("posten", "wiedervorlage", "offene punkte", "offen:")
_SECTION_GESAMTSTATUS_KEYWORDS = ("gesamtstatus", "projektstatus", "statustabelle")


def _parse_evidence_date(text: str) -> str | None:
    """Extrahiert das erste Klammerdatum aus text als ISO-String (JJJJ-MM-TT)."""
    m = _DATE_ISO_RE.search(text)
    if m:
        return m.group(0).strip("()")
    m = _DATE_DE_RE.search(text)
    if m:
        raw = m.group(0).strip("()")
        tag, mon, jahr = raw.split(".")
        return f"{jahr}-{mon}-{tag}"
    return None


def _classify_section(heading_lower: str) -> str | None:
    """Ordnet einer Ueberschrift eine Evidence-Sektion zu: 'gesamtstatus',
    'merkposten' oder None (keine Sonder-Sektion)."""
    if any(kw in heading_lower for kw in _SECTION_GESAMTSTATUS_KEYWORDS):
        return "gesamtstatus"
    if any(kw in heading_lower for kw in _SECTION_MERKPOSTEN_KEYWORDS):
        return "merkposten"
    return None

# Reine Statuswerte ohne Phasenbezug (ggf. mit Datum in Klammern) sind ohne
# Kontext wertlos und erzeugen beim Cross-Chunk-Judge False Positives
# (z.B. "abgeschlossen" vs. "abgeschlossen und real verifiziert").
_PURE_STATUS_VALUES = frozenset((
    "abgeschlossen",
    "abgeschlossen und real verifiziert",
    "offen",
    "in arbeit",
    "in arbeitung",
    "nächster schritt",
))


def _is_pure_status_value(value: str) -> bool:
    low = re.sub(r"\s+", " ", value.lower()).strip()
    low = re.sub(r"\(.*\)$", "", low).strip()  # Datumsklammer entfernen
    return low in _PURE_STATUS_VALUES


def _is_table_header_row(cells):
    c1, c2 = cells
    return "phase" in c1.lower() and "status" in c2.lower()


def _extract_table_row(line):
    m = _TABLE_ROW_RE.match(line)
    if not m:
        return None
    phase, status = m.groups()
    if _is_table_header_row((phase, status)):
        return None
    status = status.strip()
    if not status or status.upper() == "STATUS":
        return None
    phase = phase.strip()
    return f"{phase}: {status}"


def _extract_status_line(line):
    m = _STATUS_LINE_RE.match(line)
    if m:
        return m.group(1).strip()
    return None


def _extract_phase_status(line):
    """Status direkt nach Phasennummer, z.B. 'Phase 2.5: Abgeschlossen und real verifiziert'."""
    m = _PHASE_STATUS_LINE_RE.match(line)
    if not m:
        return None
    vm = _PHASE_STATUS_VALUE_RE.search(line)
    if vm:
        return (vm.group(1) + " " + vm.group(2)).strip()
    return None


def _extract_phase_header(line):
    """Liefert das Phasenlabel + Namen, z.B. 'Phase 1 — Scanner-Fundament'."""
    m = _PHASE_HEADER_RE.match(line)
    if m:
        return f"Phase {m.group(1)} — {m.group(2)}"
    return None


def _extract_keyword(line):
    """Konservativer Fallback fuer kompakte Freitext-Statusaussagen."""
    stripped = line.strip()
    if not stripped or len(stripped) > _MAX_KEYWORD_LINE_CHARS:
        return None
    if _NUMBERED_LIST_RE.match(stripped):
        return None
    # Abschnittsueberschrift im Fliesstextstil, z.B. "Bereits aus Phase 2.5 bekannt, weiterhin offen:"
    if stripped.endswith(":") and len(stripped) < 80:
        return None
    if stripped.startswith("**") or "vokabular" in stripped.lower():
        return None

    low = stripped.lower()
    # Echte "Status:"-Zeilen duerfen NICHT ueber den Keyword-Fallback
    # reinkommen -- sie werden ausschliesslich ueber _extract_status_line
    # behandelt (dort werden reine Werte ohne Phasenkontext verworfen).
    if re.match(r"(?i)^status\s*[:=]", low):
        return None
    for kw in _STATUS_KEYWORDS:
        if re.search(rf"\b{re.escape(kw)}\b", low):
            return stripped
    return None


def extract_evidence(chunk_text, chunk_index, start_line=None):
    evs = []
    seen = set()
    current_phase = None   # Kontext: zuletzt gesehene Phasenueberschrift
    current_section = None  # Kontext: "gesamtstatus", "merkposten" oder None

    for i, raw in enumerate(chunk_text.splitlines(), 1):
        line = raw.rstrip("\n").strip()
        if not line:
            continue
        if _TABLE_SEPARATOR_RE.match(line):
            continue

        # Phasen-Header: als Kontext merken, aber NICHT als eigene Evidence
        # eintragen (ein blosser Header transportiert keinen Status).
        header = _extract_phase_header(line)
        if header:
            current_phase = header
            continue

        # "## ..."-Abschnittsueberschrift: Sektion erkennen, dann weiter.
        if _SECTION_HEADING_RE.match(line):
            section = _classify_section(line[2:].strip().lower())
            if section is not None:
                current_section = section
            continue
        if any(line.startswith(p) for p in _SKIP_LINE_PREFIXES):
            continue

        fact = None
        category = None

        # 1) Markdown-Tabellenzeile (z.B. Gesamtstatus-Tabelle).
        fact = _extract_table_row(line)
        if fact:
            category = "TABELLE"

        # 2) "Status: <wert>" -- mit Phasenkontext anreichern, falls vorhanden.
        if fact is None:
            status_val = _extract_status_line(line)
            if status_val is not None:
                if current_phase:
                    fact = f"{current_phase}: {status_val}"
                    category = "PHASENABSCHNITT"
                elif not _is_pure_status_value(status_val):
                    # Ohne Phasenkontext nur behalten, wenn der Wert ueber das
                    # reine Statusvokabular hinausgeht (z.B. "ACTIVE").
                    fact = status_val
                    category = "STATUS"

        # 3) "Phase 2.5: Abgeschlossen (2026-08-24)" direkt in der Zeile.
        if fact is None:
            fact = _extract_phase_status(line)
            if fact:
                category = "PHASENABSCHNITT"

        # 4) Konservativer Freitext-Fallback (Globalaussage, Merkposten, ...).
        if fact is None:
            fact = _extract_keyword(line)
            if fact:
                low = fact.lower()
                if "alle phasen" in low:
                    category = "GESAMTAUSSAGE"
                elif current_section == "merkposten" or low.startswith("offen:"):
                    category = "MERKPOSTEN"
                else:
                    category = "PHASENABSCHNITT" if current_phase else "STATUS"

        if not fact:
            continue

        fact = re.sub(r"\s+", " ", fact).strip()
        if len(fact) < 5 or fact in seen:
            continue
        seen.add(fact)

        actual = start_line + i - 1 if start_line is not None else None
        evs.append(Evidence(
            chunk_index=chunk_index,
            text=fact,
            start_line=actual,
            category=category,
            date=_parse_evidence_date(fact),
        ))

    return evs