"""Gateway LLM: instradamento per funzione e per riservatezza.

Un solo formato di chiamata (API compatibile OpenAI: fornitore diretto, OpenRouter,
vLLM, Ollama...) e tre profili:
- `local`: modello sul server, ammesso per tutte le fonti;
- `cloud_fast`: compiti medi, solo fonti normali;
- `cloud_strong`: compiti difficili, solo fonti normali.

Regole:
1. Se nel contesto c'è anche una sola fonte riservata o segreta, si usa solo il
   profilo locale (vince il livello più restrittivo).
2. Altrimenti decide il livello della funzione: i compiti semplici preferiscono il
   modello locale, quelli difficili il cloud più capace; se un profilo manca si
   ripiega sul più vicino.

Il testo delle fonti è sempre trattato come dato: l'LLM non ha strumenti né effetti collaterali.
"""

import enum
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass

import httpx

from app.config import get_settings
from app.models import Confidentiality


class LlmUnavailable(RuntimeError):
    pass


class LlmError(RuntimeError):
    pass


class Tier(enum.IntEnum):
    simple = 1
    medium = 2
    hard = 3


class Task(str, enum.Enum):
    """Le funzioni che usano un LLM, ognuna con il suo livello."""

    clean = "clean"  # versione pulita della trascrizione
    extract = "extract"  # estrazione di entità e cifre
    summarize = "summarize"  # sintesi, temi, citazioni salienti
    resolve = "resolve"  # proposte di unione delle entità
    ask = "ask"  # domande sull'archivio con citazioni
    write = "write"  # scaletta, titoli, adattamento di formato
    verify = "verify"  # verifica della bozza contro le fonti

    @property
    def tier(self) -> Tier:
        return {
            Task.clean: Tier.simple,
            Task.extract: Tier.simple,
            Task.summarize: Tier.medium,
            Task.resolve: Tier.medium,
            Task.ask: Tier.hard,
            Task.write: Tier.hard,
            Task.verify: Tier.hard,
        }[self]


@dataclass(frozen=True)
class Profile:
    name: str
    base_url: str
    api_key: str | None
    model: str

    @property
    def is_local(self) -> bool:
        return self.name == "local"


def _local() -> Profile | None:
    s = get_settings()
    if s.llm_local_base_url and s.llm_local_model:
        return Profile("local", s.llm_local_base_url, s.llm_local_api_key, s.llm_local_model)
    return None


def _cloud(kind: str) -> Profile | None:
    s = get_settings()
    model = (s.llm_cloud_fast_model if kind == "fast" else s.llm_cloud_strong_model) or s.llm_cloud_model
    if s.llm_cloud_api_key and model:
        return Profile(f"cloud_{kind}", s.llm_cloud_base_url, s.llm_cloud_api_key, model)
    return None


def restricted(levels: Iterable[Confidentiality]) -> bool:
    return any(c != Confidentiality.normal for c in levels)


def route(task: Task, levels: Iterable[Confidentiality]) -> Profile | None:
    """Il profilo da usare per `task` su un contesto con queste riservatezze (None = nessuno)."""
    if restricted(list(levels)):
        return _local()
    tier = task.tier
    if tier == Tier.simple:
        order = [_local, lambda: _cloud("fast"), lambda: _cloud("strong")]
        if not get_settings().llm_prefer_local_for_simple:
            order = order[1:] + order[:1]
    elif tier == Tier.medium:
        order = [lambda: _cloud("fast"), lambda: _cloud("strong"), _local]
    else:
        order = [lambda: _cloud("strong"), lambda: _cloud("fast"), _local]
    for candidate in order:
        profile = candidate()
        if profile is not None:
            return profile
    return None


def unavailable_reason(levels: Iterable[Confidentiality]) -> str:
    if restricted(list(levels)):
        return "Le fonti riservate richiedono un modello locale, non ancora configurato"
    return "Nessun modello linguistico configurato"


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
