"""Motori di trascrizione intercambiabili.

- `faster-whisper`: Whisper su CTranslate2, CPU o GPU, con tempi per parola e VAD.
- `fake`: deterministico, per i test (non scarica modelli).

I modelli si caricano una volta per processo del worker.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from app.config import get_settings
from app.pipeline.segmentation import Word

log = logging.getLogger(__name__)

ProgressFn = Callable[[float], None]  # 0..1


@dataclass
class SttResult:
    language: str | None
    duration: float
    words: list[Word]


class Engine:
    name: str
    model: str
    needs_wav: bool = True

    def transcribe(self, audio: Path, samples, language: str | None, progress: ProgressFn) -> SttResult:
        """`samples`: PCM float32 16 kHz mono già decodificato da ffmpeg (None se needs_wav è False)."""
        raise NotImplementedError


class FasterWhisperEngine(Engine):
    name = "faster-whisper"
    _models: dict[tuple, object] = {}

    def __init__(self, model: str, device: str, compute_type: str):
        self.model = model
        self.device = device
        self.compute_type = compute_type

    def _load(self):
        from faster_whisper import WhisperModel

        device = self.device
        if device == "auto":
            try:
                import ctranslate2

                device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
            except Exception:
                device = "cpu"
        compute = self.compute_type
        if compute == "default":
            compute = "float16" if device == "cuda" else "int8"
        key = (self.model, device, compute)
        if key not in self._models:
            log.info("Carico il modello %s su %s (%s)", self.model, device, compute)
            self._models[key] = WhisperModel(self.model, device=device, compute_type=compute)
        return self._models[key]

    def transcribe(self, audio: Path, samples, language: str | None, progress: ProgressFn) -> SttResult:
        model = self._load()
        # Si passano i campioni già decodificati: niente seconda decodifica (PyAV) dentro faster-whisper.
        segments, info = model.transcribe(
            samples,
            language=language,
            word_timestamps=True,
            vad_filter=True,
            beam_size=5,
            # Evita i "loop" di ripetizioni tipici di Whisper sulle registrazioni lunghe
            condition_on_previous_text=False,
        )
        duration = float(info.duration or 0.0)
        words: list[Word] = []
        for seg in segments:  # generatore: la trascrizione avanza mentre si itera
            for w in seg.words or []:
                if w.word.strip():
                    # Lo spazio iniziale segna l'inizio di una parola nuova: va conservato
                    words.append([w.word, round(w.start, 2), round(w.end, 2), round(w.probability, 2)])
            if duration:
                progress(min(seg.end / duration, 1.0))
        return SttResult(language=info.language, duration=duration, words=words)


class FakeEngine(Engine):
    """Restituisce un testo fisso distribuito su 10 secondi. Solo per i test."""

    name = "fake"
    model = "fake"
    needs_wav = False
    TEXT = (
        "Buongiorno, sono l'assessore Mario Rossi. Il depuratore costa 4,5 milioni di euro. "
        "I lavori partiranno nel 2027, non prima."
    )

    def transcribe(self, audio: Path, samples, language: str | None, progress: ProgressFn) -> SttResult:
        tokens = self.TEXT.split()
        step = 10.0 / len(tokens)
        words = [
            [" " + t, round(i * step, 2), round((i + 1) * step - 0.05, 2), 0.9] for i, t in enumerate(tokens)
        ]
        progress(1.0)
        return SttResult(language=language or "it", duration=10.0, words=words)


def get_engine() -> Engine:
    s = get_settings()
    if s.stt_engine == "fake":
        return FakeEngine()
    if s.stt_engine == "faster-whisper":
        return FasterWhisperEngine(s.stt_model, s.stt_device, s.stt_compute_type)
    raise ValueError(f"Motore di trascrizione sconosciuto: {s.stt_engine}")
