"""Client dell'embedder interno."""

import httpx

from app.config import get_settings


class EmbedderUnavailable(RuntimeError):
    pass


def embed(texts: list[str], *, timeout: float | None = None) -> list[list[float]]:
    s = get_settings()
    out: list[list[float]] = []
    for i in range(0, len(texts), 64):
        try:
            r = httpx.post(
                s.embedder_url.rstrip("/") + "/embed",
                json={"texts": texts[i : i + 64]},
                timeout=timeout or s.embedder_timeout_seconds,
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise EmbedderUnavailable("Servizio di embeddings non raggiungibile") from exc
        out.extend(r.json()["vectors"])
    return out
