"""
agents/evaluator_agent/model_clients.py

NEUES Modul (2026-08-26, Cloud-Eskalation -- siehe Chat-Verlauf).

Grund: der lokale Patch-Writer (qwen2.5:latest UND qwen2.5-coder:latest)
hat in mehreren realen Testlaeufen bei derselben Formulierungsaufgabe
(Hunk + Volltext -> exact_old_text/replacement_text-Patch) verlaesslich,
aber jeweils UNTERSCHIEDLICH fehlgeschlagen: falsche Zielzeile getroffen,
ungueltiges Zitat + zu grosse Ersetzung, falsche Zielzeile trotz validem
Zitat. Drei verschiedene Fehlerarten bei derselben Aufgabe ueber zwei
Modelle hinweg ist ein robustes Signal fuer eine Modell-Faehigkeitsgrenze,
nicht (nur) ein Kontext-/Prompt-Problem (im Gegensatz zum Judge, der nach
dem Vollkontext-Fix zuverlaessig funktionierte).

Dieses Modul kapselt die REST-Aufrufe zu zwei kostenlosen Cloud-APIs als
Fallback-Stufen, WENN Ollama technisch fehlschlaegt ODER der erzeugte
Patch die deterministische Validierung (patching/patch_validator.py)
nicht besteht:

1. Google Gemini (gemini-2.5-pro, Free Tier ueber Google AI Studio)
2. Groq (llama-3.3-70b-versatile, Free Tier ueber GroqCloud)

WICHTIG: dieses Modul aendert NICHTS am Sicherheitsprinzip aus dem
Handover (Abschnitt 3) -- JEDER von hier zurueckgegebene Patch-Vorschlag
durchlaeuft weiterhin dieselbe harte, deterministische Validierung
(patch_validator.py) und Human-in-the-Loop-Bestaetigung wie ein
Ollama-Vorschlag. Cloud-Modelle liefern hier NUR einen alternativen
Formulierungsversuch, keine automatische Schreibberechtigung.

Beide Funktionen erwarten den bereits fertig zusammengebauten Prompt-Text
(build_patch_writer_prompt()-Ergebnis) als Parameter -- dieselbe
Prompt-Logik wird fuer alle drei Anbieter wiederverwendet, nur der
Transport-/Antwort-Parsing-Code unterscheidet sich je Anbieter.
"""

from __future__ import annotations

import os
import re
import time

import requests

GEMINI_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
)
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

DEFAULT_GEMINI_MODEL = "gemini-3-flash-preview"
DEFAULT_GROQ_MODEL = "openai/gpt-oss-120b"


class ModelClientError(Exception):
    """Fehler beim Aufruf einer Cloud-Modell-API oder beim Parsen der Antwort."""


def call_gemini(
    prompt: str,
    model: str = DEFAULT_GEMINI_MODEL,
    timeout_seconds: int = 90,
) -> str:
    """Ruft die Gemini API auf und gibt den rohen Antworttext zurueck
    (noch NICHT als JSON geparst -- das macht der Aufrufer, analog zum
    bestehenden Ollama-Umgang in patch_writer.py)."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ModelClientError("GEMINI_API_KEY nicht in Umgebungsvariablen gefunden (.env pruefen).")

    url = GEMINI_URL_TEMPLATE.format(model=model, api_key=api_key)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }

    try:
        response = requests.post(url, json=payload, timeout=timeout_seconds)
        response.raise_for_status()
    except requests.exceptions.Timeout as exc:
        raise ModelClientError(f"Gemini Timeout nach {timeout_seconds}s.") from exc
    except requests.exceptions.HTTPError as exc:
        raise ModelClientError(f"Gemini HTTP-Fehler: {exc}\nAntwort: {response.text[:500]}") from exc
    except requests.exceptions.RequestException as exc:
        raise ModelClientError(f"Gemini nicht erreichbar: {exc}") from exc

    body = response.json()

    try:
        return body["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as exc:
        raise ModelClientError(
            f"Gemini-Antwort hat unerwartete Struktur: {exc}.\nRohantwort: {str(body)[:500]}"
        ) from exc


def call_groq(
    prompt: str,
    model: str = DEFAULT_GROQ_MODEL,
    timeout_seconds: int = 90,
    max_retries_on_429: int = 1,
) -> str:
    """Ruft die Groq API auf (OpenAI-kompatibles Format) und gibt den
    rohen Antworttext zurueck.

    Bei HTTP 429 (Rate Limit) wird EINMALIG die vom Server mitgeteilte
    Retry-After-Zeit (bzw. die im Fehlertext genannte Sekundenzahl) abgewartet
    und der Request wiederholt. Danach wird ein ModelClientError geworfen --
    bewusst kein endloser Backoff, damit der Audit bei wiederholten Limits
    sauber abbrechen statt haengen bleibt.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ModelClientError("GROQ_API_KEY nicht in Umgebungsvariablen gefunden (.env pruefen).")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    retries = 0
    while True:
        try:
            response = requests.post(GROQ_URL, json=payload, headers=headers, timeout=timeout_seconds)
            if response.status_code == 429 and retries < max_retries_on_429:
                retries += 1
                wait_seconds = _groq_retry_after(response)
                print(
                    f"  Groq 429 (Rate-Limit) erkannt -- warte {wait_seconds:.0f}s "
                    f"und wiederhole (Versuch {retries}/{max_retries_on_429})..."
                )
                time.sleep(wait_seconds)
                continue
            response.raise_for_status()
        except requests.exceptions.Timeout as exc:
            raise ModelClientError(f"Groq Timeout nach {timeout_seconds}s.") from exc
        except requests.exceptions.HTTPError as exc:
            raise ModelClientError(f"Groq HTTP-Fehler: {exc}\nAntwort: {response.text[:500]}") from exc
        except requests.exceptions.RequestException as exc:
            raise ModelClientError(f"Groq nicht erreichbar: {exc}") from exc

        body = response.json()

        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise ModelClientError(
                f"Groq-Antwort hat unerwartete Struktur: {exc}.\nRohantwort: {str(body)[:500]}"
            ) from exc


def _groq_retry_after(response) -> float:
    """Ermittelt die Wartezeit fuer einen 429-Retry:
    1. HTTP-Header 'Retry-After' (in Sekunden),
    2. sonst aus der Fehlermeldung 'try again in <n>s' (Groq-Format),
    3. sonst Standard 30s.
    """
    retry_after = response.headers.get("Retry-After")
    if retry_after:
        try:
            return float(retry_after)
        except ValueError:
            pass
    m = re.search(r"try again in\s+([\d.]+)\s*s", response.text or "", re.IGNORECASE)
    if m:
        return float(m.group(1)) + 2.0  # kleine Reserve
    return 30.0
