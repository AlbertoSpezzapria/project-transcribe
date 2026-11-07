"""Acquisizione di pagine web: copia salvata ed estrazione dell'articolo.

Sicurezza (SSRF): il server scarica indirizzi forniti dagli utenti, quindi
- solo http/https sulle porte standard;
- l'host deve risolvere solo a indirizzi pubblici (niente rete interna, localhost,
  metadati del cloud), controllato a ogni redirect;
- limiti di dimensione, tempo e numero di redirect.
Resta un rischio residuo di DNS rebinding tra controllo e connessione: in produzione
il worker va comunque messo su una rete con uscita filtrata (vedi DESIGN §12).
"""

import ipaddress
import socket
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urljoin, urlsplit

import httpx

from app.config import get_settings

MAX_REDIRECTS = 5
HTML_TYPES = ("text/html", "application/xhtml+xml")
PDF_TYPE = "application/pdf"


class FetchError(RuntimeError):
    pass


@dataclass
class Fetched:
    url: str  # finale, dopo i redirect
    content_type: str
    body: bytes
    status: int
    fetched_at: datetime
    redirects: list[str] = field(default_factory=list)


def check_url(url: str) -> str:
    """Normalizza e valida un indirizzo fornito dall'utente (senza rete)."""
    url = url.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise FetchError("Serve un indirizzo che inizi con http:// o https://")
    if parts.username or parts.password:
        raise FetchError("Indirizzi con credenziali non ammessi")
    if parts.port not in (None, 80, 443):
        raise FetchError("Porta non ammessa")
    return url


def _check_host(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise FetchError("Indirizzo non raggiungibile (dominio inesistente?)") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise FetchError("Indirizzo non ammesso (rete interna)")


def fetch(url: str) -> Fetched:
    s = get_settings()
    url = check_url(url)
    redirects: list[str] = []
    headers = {"User-Agent": s.web_user_agent, "Accept": "text/html,application/xhtml+xml,application/pdf"}
    with httpx.Client(follow_redirects=False, timeout=s.web_timeout_seconds, headers=headers) as client:
        for _ in range(MAX_REDIRECTS + 1):
            _check_host(urlsplit(url).hostname or "")
            try:
                with client.stream("GET", url) as r:
                    if r.is_redirect:
                        nxt = urljoin(url, r.headers.get("location", ""))
                        redirects.append(url)
                        url = check_url(nxt)
                        continue
                    if r.status_code >= 400:
                        raise FetchError(f"La pagina ha risposto con errore {r.status_code}")
                    ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
                    if ctype not in HTML_TYPES and ctype != PDF_TYPE:
                        raise FetchError(f"Tipo di contenuto non supportato: {ctype or 'sconosciuto'}")
                    body = bytearray()
                    for chunk in r.iter_bytes():
                        body.extend(chunk)
                        if len(body) > s.web_max_bytes:
                            raise FetchError("Pagina troppo grande")
                    return Fetched(
                        url=url,
                        content_type=ctype,
                        body=bytes(body),
                        status=r.status_code,
                        fetched_at=datetime.now(UTC),
                        redirects=redirects,
                    )
            except httpx.TimeoutException as exc:
                raise FetchError("La pagina non ha risposto in tempo") from exc
            except httpx.HTTPError as exc:
                raise FetchError("Impossibile scaricare la pagina") from exc
    raise FetchError("Troppi reindirizzamenti")


@dataclass
class Article:
    title: str | None
    author: str | None
    date: str | None  # ISO, se la pagina la dichiara
    site: str | None
    text: str


def extract_article(html: bytes, url: str) -> Article:
    import trafilatura

    doc = trafilatura.bare_extraction(
        html.decode("utf-8", errors="replace"),
        url=url,
        include_comments=False,
        include_tables=True,
        favor_precision=True,
        with_metadata=True,
    )
    if doc is None:
        return Article(None, None, None, None, "")
    get = (lambda k: getattr(doc, k, None)) if not isinstance(doc, dict) else doc.get
    return Article(
        title=get("title"),
        author=get("author"),
        date=get("date"),
        site=get("sitename") or get("hostname"),
        text=get("text") or "",
    )
