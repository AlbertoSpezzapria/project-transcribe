"""Riconoscimento degli interlocutori con pyannote (opzionale).

Serve l'extra `diarization` (torch + pyannote.audio) e un token Hugging Face
con la licenza del modello accettata. I modelli girano in locale: l'audio non
lascia il server.
"""

import logging
from collections.abc import Callable

from app.config import get_settings
from app.pipeline.segmentation import Turn

log = logging.getLogger(__name__)

_pipeline = None


class DiarizationUnavailable(RuntimeError):
    pass


def configured() -> bool:
    """Attivata nella configurazione (l'API non ha pyannote installato: lo usa solo il worker)."""
    s = get_settings()
    return bool(s.diarization_enabled and s.hf_token)


def available() -> bool:
    if not configured():
        return False
    try:
        import pyannote.audio  # noqa: F401
    except ImportError:
        return False
    return True


def _load():
    global _pipeline
    if _pipeline is None:
        try:
            import torch
            from pyannote.audio import Pipeline
        except ImportError as exc:
            raise DiarizationUnavailable("pyannote.audio non installato") from exc
        s = get_settings()
        try:
            pipeline = Pipeline.from_pretrained(s.diarization_model, token=s.hf_token)
        except Exception as exc:
            text = str(exc)
            if "gated" in text.lower() or "403" in text:
                raise DiarizationUnavailable(
                    f"Licenza del modello {s.diarization_model} non ancora accettata su Hugging Face"
                ) from exc
            if "401" in text:
                raise DiarizationUnavailable("Token Hugging Face non valido") from exc
            raise DiarizationUnavailable("Modello di riconoscimento delle voci non scaricabile") from exc
        if pipeline is None:
            raise DiarizationUnavailable("Modello di diarization non accessibile (licenza o token)")
        if torch.cuda.is_available():
            pipeline.to(torch.device("cuda"))
        _pipeline = pipeline
    return _pipeline


def diarize(samples, sample_rate: int, progress: Callable[[float], None]) -> list[Turn]:
    import torch

    pipeline = _load()

    def hook(step_name, step_artifact, file=None, total=None, completed=None):
        if total and completed is not None:
            progress(min(completed / total, 1.0))

    waveform = torch.from_numpy(samples).unsqueeze(0)
    output = pipeline({"waveform": waveform, "sample_rate": sample_rate}, hook=hook)
    # pyannote 4: preferisce la versione "esclusiva" (un solo speaker per istante),
    # più adatta ad assegnare le parole. pyannote 3: oggetto Annotation diretto.
    annotation = getattr(output, "exclusive_speaker_diarization", None) or getattr(
        output, "speaker_diarization", output
    )
    turns = [
        Turn(start=float(seg.start), end=float(seg.end), speaker=str(label))
        for seg, _, label in annotation.itertracks(yield_label=True)
    ]
    progress(1.0)
    return turns
