"""
patching/patch_validator.py

Deterministische Validierung eines ProposedPatch, BEVOR er dem Nutzer
angezeigt wird (2026-08-25). Das ist die zentrale Sicherheitsschicht des
gesamten neuen Patch-Workflows -- ersetzt ALLE vorherigen, schwaecheren
Validierungsversuche (proposal_validation.py alt: nur Laengen-/Zeilenzahl-
Heuristik, konnte den "eigenen" -> "own"-Fehler NICHT fangen).

WARUM DIESER ANSATZ DEN FRUEHEREN FEHLER STRUKTURELL AUSSCHLIESST:
Ein Patch besteht aus exact_old_text/replacement_text. validate_patch()
prueft ZUERST, ob exact_old_text ueberhaupt WORTWOERTLICH im Dokument
vorkommt -- und zwar GENAU EINMAL. Gibt es KEINEN oder MEHRERE Treffer,
wird der Patch automatisch abgelehnt, OHNE dass irgendein Text angezeigt
oder angewendet wird. Das ist der entscheidende Unterschied zu allen
vorherigen Versionen: dort wurde IMMER ein neuer Text vom Modell
akzeptiert und nur nachtraeglich auf Plausibilitaet (Laenge, Marker-
Woerter) geprueft -- hier wird die Anwendbarkeit selbst zur harten
Vorbedingung.

Ein Patch, der diese Pruefung besteht, kann NIEMALS versehentlich Text
ausserhalb von exact_old_text veraendern, weil die Anwendung
(patch_applier.py) spaeter nur exact_old_text durch replacement_text
ERSETZT -- der Rest der Datei wird nie angefasst, ist also strukturell
geschuetzt.
"""

from __future__ import annotations

from dataclasses import dataclass

from patching.patch_models import ProposedPatch, ValidatedPatch

MAX_OLD_TEXT_LENGTH = 2000  # ein Patch soll klein/lokal bleiben, kein Freibrief fuer grosse Bloecke
MAX_LENGTH_RATIO = 3.0  # replacement darf max. 3x so lang sein wie exact_old_text
MIN_OLD_TEXT_LENGTH = 3  # verhindert Patches auf trivial kurze/mehrdeutige Fragmente

PROMPT_LEAK_MARKERS = [
    "antworte ausschließlich",
    "json-objekt",
    "exact_old_text",
    "replacement_text",
    "wichtige einschränkungen",
]


@dataclass(frozen=True)
class PatchValidationResult:
    passed: bool
    failures: list[str]
    validated_patch: ValidatedPatch | None


def validate_patch(patch: ProposedPatch, current_full_text: str) -> PatchValidationResult:
    """Fuehrt ALLE Sicherheitschecks aus, IN DIESER REIHENFOLGE (fruehe,
    harte Ablehnungsgruende zuerst, um unnoetige weitere Pruefungen zu
    vermeiden -- reine Lesbarkeits-/Effizienz-Entscheidung, kein
    Sicherheitsgewinn durch die Reihenfolge selbst)."""
    failures: list[str] = []

    if not patch.exact_old_text.strip():
        return PatchValidationResult(
            passed=False, failures=["exact_old_text ist leer."], validated_patch=None
        )

    if len(patch.exact_old_text) < MIN_OLD_TEXT_LENGTH:
        failures.append(
            f"exact_old_text ist zu kurz ({len(patch.exact_old_text)} Zeichen, "
            f"Minimum {MIN_OLD_TEXT_LENGTH}) -- zu unspezifisch, Risiko falscher Treffer."
        )

    if len(patch.exact_old_text) > MAX_OLD_TEXT_LENGTH:
        failures.append(
            f"exact_old_text ist zu lang ({len(patch.exact_old_text)} Zeichen, "
            f"Maximum {MAX_OLD_TEXT_LENGTH}) -- Patch soll klein/lokal bleiben."
        )

    occurrence_count = current_full_text.count(patch.exact_old_text)
    if occurrence_count == 0:
        failures.append(
            "exact_old_text kommt NICHT WORTWOERTLICH im aktuellen Dokument vor. "
            "Entweder hat sich die Datei seit der Analyse geaendert, oder das Modell "
            "hat den Text nicht exakt zitiert (z.B. Tippfehler, andere Leerzeichen/"
            "Zeilenumbrueche)."
        )
    elif occurrence_count > 1:
        failures.append(
            f"exact_old_text kommt {occurrence_count}x im Dokument vor -- nicht eindeutig "
            f"genug fuer eine sichere automatische Ersetzung. Patch muss praeziser/laenger "
            f"formuliert werden, um eindeutig zu sein."
        )

    length_ratio = len(patch.replacement_text) / max(len(patch.exact_old_text), 1)
    if length_ratio > MAX_LENGTH_RATIO:
        failures.append(
            f"replacement_text ist {length_ratio:.1f}x so lang wie exact_old_text "
            f"(Grenze: {MAX_LENGTH_RATIO}x) -- moeglicher Prompt-Leak oder unangemessen "
            f"grosse Aenderung fuer einen lokalen Patch."
        )

    lower_replacement = patch.replacement_text.lower()
    for marker in PROMPT_LEAK_MARKERS:
        if marker in lower_replacement:
            failures.append(f"Verdacht auf Prompt-Leak: Phrase '{marker}' im replacement_text gefunden.")

    if patch.exact_old_text.strip() == patch.replacement_text.strip():
        failures.append("replacement_text ist identisch zu exact_old_text -- Patch aendert nichts.")

    if failures:
        return PatchValidationResult(passed=False, failures=failures, validated_patch=None)

    occurrence_start_index = current_full_text.index(patch.exact_old_text)

    validated = ValidatedPatch(
        filename=patch.filename,
        exact_old_text=patch.exact_old_text,
        replacement_text=patch.replacement_text,
        change_summary=patch.change_summary,
        occurrence_start_index=occurrence_start_index,
    )
    return PatchValidationResult(passed=True, failures=[], validated_patch=validated)
