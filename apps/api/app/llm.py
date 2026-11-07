"""Gateway LLM con instradamento per riservatezza.

Un solo formato (API compatibile OpenAI: OpenRouter, vLLM, Ollama, ...), due profili:
- `cloud`: ammesso solo per le fonti normali (fornitore con zero data retention);
- `local`: modello sul server, ammesso per tutte le fonti.

Il testo delle fonti è sempre trattato come dato: l'LLM non ha strumenti né effetti collaterali.
"""

import json
import re
from dataclasses import dataclass

import httpx

from app.config import get_settings
from app.models import Confidentiality


class LlmUnavailable(RuntimeError):
    pass


class LlmError(RuntimeError):
    pass


@dataclass(frozen=True)
class Profile:
    name: str
    base_url: str
    api_key: str | None
    model: str


def _local() -> Profile | None:
    s = get_settings()
    if s.llm_local_base_url and s.llm_local_model:
        return Profile("local", s.llm_local_base_url, s.llm_local_api_key, s.llm_local_model)
    return None


def _cloud() -> Profile | None:
    s = get_settings()
    if s.llm_cloud_api_key and s.llm_cloud_model:
        return Profile("cloud", s.llm_cloud_base_url, s.llm_cloud_api_key, s.llm_cloud_model)
    return None


def profile_for(confidentiality: Confidentiality) -> Profile | None:
    """Le fonti riservate e segrete non escono mai dal server."""
    if confidentiality == Confidentiality.normal:
        return _cloud() or _local()
    return _local()


def unavailable_reason(confidentiality: Confidentiality) -> str:
    if confidentiality == Confidentiality.normal:
        return "Nessun modello linguistico configurato"
    return "Le fonti riservate richiedono un modello locale, non ancora configurato"


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


def chat_json(profile: Profile, system: str, user: str) -> dict:
    """Una richiesta, risposta in JSON. Nessuna cronologia, nessuno strumento."""
    headers = {"Content-Type": "application/json"}
    if profile.api_key:
        headers["Authorization"] = f"Bearer {profile.api_key}"
    body = {
        "model": profile.model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    try:
        r = httpx.post(
            profile.base_url.rstrip("/") + "/chat/completions",
            json=body,
            headers=headers,
            timeout=get_settings().llm_timeout_seconds,
        )
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"] or ""
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise LlmError(f"Errore del modello linguistico: {type(exc).__name__}") from exc
    try:
        return json.loads(_FENCE.sub("", content).strip())
    except json.JSONDecodeError as exc:
        raise LlmError("Risposta del modello non in formato JSON") from exc
