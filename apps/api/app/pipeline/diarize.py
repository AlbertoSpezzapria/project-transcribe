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


def available() -> bool:
    s = get_settings()
    if not (s.diarization_enabled and s.hf_token):
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
        pipeline = Pipeline.from_pretrained(s.diarization_model, token=s.hf_token)
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
