"""
patching/patch_applier.py

Wendet einen bereits VALIDIERTEN Patch (ValidatedPatch) deterministisch
an -- reine String-Ersetzung, kein LLM, kein Raten (2026-08-25).

WICHTIG: apply_patch() prueft ERNEUT (kurz vor dem Schreiben), ob
exact_old_text noch GENAU EINMAL im aktuellen Dateiinhalt vorkommt --
das faengt den Fall ab, dass sich die Datei zwischen Validierung und
tatsaechlichem Schreiben veraendert hat (z.B. Nutzer hat parallel etwas
bearbeitet, oder mehrere Patches derselben Datei wurden nacheinander
bearbeitet und ein vorheriger Patch hat den Text bereits veraendert).
Diese zweite Pruefung ist bewusst redundant zu patch_validator.py --
Sicherheitsprinzip "defense in depth", nicht Doppelarbeit ohne Grund.
"""

from __future__ import annotations

from patching.patch_models import PatchApplicationResult, ValidatedPatch


def apply_patch(current_full_text: str, patch: ValidatedPatch) -> PatchApplicationResult:
    """Ersetzt exact_old_text durch replacement_text. Gibt bei Erfolg den
    kompletten neuen Volltext zurueck -- schreibt NICHT selbst in eine
    Datei (siehe run_drift_check.py fuer den tatsaechlichen Schreibvorgang
    nach Nutzer-Bestaetigung, konsistent mit dem Human-in-the-Loop-Prinzip)."""
    occurrence_count = current_full_text.count(patch.exact_old_text)

    if occurrence_count == 0:
        return PatchApplicationResult(
            success=False,
            updated_full_text=None,
            error_message=(
                "exact_old_text kommt nicht mehr im aktuellen Dokument vor -- "
                "Datei wurde vermutlich seit der Validierung veraendert (z.B. durch "
                "einen vorherigen, bereits angewendeten Patch in diesem Lauf)."
            ),
        )

    if occurrence_count > 1:
        return PatchApplicationResult(
            success=False,
            updated_full_text=None,
            error_message=(
                f"exact_old_text kommt jetzt {occurrence_count}x vor (war bei Validierung "
                f"eindeutig) -- Anwendung abgebrochen, um keine falsche Stelle zu treffen."
            ),
        )

    updated_full_text = current_full_text.replace(patch.exact_old_text, patch.replacement_text, 1)

    return PatchApplicationResult(success=True, updated_full_text=updated_full_text, error_message=None)
