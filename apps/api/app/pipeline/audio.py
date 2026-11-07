"""Normalizzazione dell'audio e forma d'onda per il player.

Richiede ffmpeg (presente nell'immagine del worker di trascrizione) e numpy.
"""

import subprocess
from pathlib import Path

SAMPLE_RATE = 16_000


class AudioError(RuntimeError):
    pass


def normalize(src: Path, dst: Path) -> Path:
    """Qualsiasi audio/video → WAV 16 kHz mono 16 bit (formato atteso da STT e diarization)."""
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-i", str(src),
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-c:a", "pcm_s16le",
        str(dst),
    ]  # fmt: skip
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if proc.returncode != 0 or not dst.exists() or dst.stat().st_size <= 44:
        raise AudioError("Il file non contiene una traccia audio leggibile")
    return dst


def load_pcm(wav: Path):
    """Campioni float32 in [-1, 1] dal WAV prodotto da `normalize`."""
    import numpy as np

    data = np.fromfile(wav, dtype=np.int16, offset=44)
    return data.astype(np.float32) / 32768.0


def peaks(samples, buckets: int = 1600) -> list[float]:
    """Picchi per intervallo, normalizzati 0..1 e arrotondati (pochi KB per ore di audio)."""
    import numpy as np

    n = len(samples)
    if n == 0:
        return []
    buckets = max(1, min(buckets, n))
    usable = n - (n % buckets)
    blocks = np.abs(samples[:usable]).reshape(buckets, -1).max(axis=1)
    top = float(blocks.max()) or 1.0
    return [round(float(v) / top, 3) for v in blocks]
