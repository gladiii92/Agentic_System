from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Evidence:
    """Leichte Repräsentation eines extrahierten Fakten/Statements aus einem Chunk.

    ``category`` klassifiziert die Herkunft einer Aussage, damit der
    Cross-Chunk-Judge Tabellenzeilen, Phasenabschnitte, Globalaussagen und
    Merkposten unterscheiden kann:

      - "TABELLE"          -> Zeile der Gesamtstatus-Tabelle
      - "PHASENABSCHNITT"  -> Status im Abschnitt einer einzelnen Phase
      - "GESAMTAUSSAGE"    -> zusammenfassende Globalaussage (z.B. Fazit-Satz)
      - "MERKPOSTEN"       -> offener Punkt / Merkposten / TODO
      - "STATUS"           -> sonstige Statusangabe (z.B. Dokument-Status)

    ``date`` (ISO: JJJJ-MM-TT) wird aus Klammer-Datumsangaben im Originaltext
    extrahiert, falls vorhanden. Es ist die Grundlage der Datums-Rangfolgen-
    Regel ("die neueste datierte Aussage ist die Wahrheit").
    """

    chunk_index: int
    text: str
    start_line: int | None = None
    category: str | None = None
    date: str | None = None

    @property
    def compact(self) -> str:
        """Kompakte Textrepräsentation für den Prompt.

        Enthält den Kategorie-Tag (z.B. ``[TABELLE]``) und -- falls im Text
        nicht bereits enthalten -- das Klammerdatum, damit der Cross-Chunk-
        Judge die Herkunft und den Stand jeder Aussage erkennt.
        """
        parts: list[str] = []
        if self.category:
            parts.append(f"[{self.category}]")
        if self.start_line is not None:
            parts.append(f"Zeilen {self.start_line}:")
        parts.append(self.text)
        if self.date and self.date not in self.text:
            parts.append(f"(Stand: {self.date})")
        return " ".join(parts)