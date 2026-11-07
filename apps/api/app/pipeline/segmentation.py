"""Dalle parole con i tempi ai segmenti citabili (turni di parola).

Funzioni pure, senza dipendenze pesanti: si testano senza modelli.

Una parola è una tupla compatta `[testo, inizio, fine, probabilità]`, la stessa
forma salvata nel database e inviata al frontend. Il testo conserva lo spazio
iniziale prodotto dal modello: indica dove comincia una parola nuova (così
"l'" + "ufficio" resta "l'ufficio" e non diventa "l' ufficio").
"""

from dataclasses import dataclass, field

Word = list  # [text: str, start: float, end: float, prob: float]

_SENTENCE_END = (".", "?", "!", "…")


@dataclass(frozen=True)
class Turn:
    """Intervallo in cui parla un interlocutore (output della diarization)."""

    start: float
    end: float
    speaker: str


@dataclass
class BuiltSegment:
    start: float
    end: float
    speaker: str | None
    words: list[Word] = field(default_factory=list)

    @property
    def text(self) -> str:
        return join_words(self.words)


def join_words(words: list[Word]) -> str:
    return "".join(w[0] for w in words).strip()


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def assign_speakers(words: list[Word], turns: list[Turn]) -> list[str | None]:
    """Per ogni parola, lo speaker con la sovrapposizione temporale maggiore.

    Se una parola cade in una pausa tra due turni, prende il turno più vicino
    (entro 1 secondo), altrimenti lo speaker della parola precedente.
    """
    if not turns:
        return [None] * len(words)
    turns = sorted(turns, key=lambda t: t.start)
    result: list[str | None] = []
    j = 0  # primo turno che può ancora sovrapporsi (le parole sono in ordine)
    for _text, start, end, *_ in words:
        while j < len(turns) and turns[j].end < start - 1.0:
            j += 1
        best, best_ov = None, 0.0
        nearest, nearest_d = None, 1.0
        k = j
        while k < len(turns) and turns[k].start <= end + 1.0:
            t = turns[k]
            ov = _overlap(start, end, t.start, t.end)
            if ov > best_ov:
                best, best_ov = t.speaker, ov
            d = max(t.start - end, start - t.end, 0.0)
            if d < nearest_d:
                nearest, nearest_d = t.speaker, d
            k += 1
        speaker = best or nearest or (result[-1] if result else None)
        result.append(speaker)
    return result


def build_segments(
    words: list[Word],
    turns: list[Turn] | None = None,
    *,
    target_seconds: float = 30.0,
    max_seconds: float = 60.0,
    pause_seconds: float = 2.0,
) -> list[BuiltSegment]:
    """Raggruppa le parole in segmenti leggibili e citabili.

    Si apre un nuovo segmento quando:
    - cambia l'interlocutore;
    - c'è una pausa lunga;
    - il segmento supera `target_seconds` e la parola precedente chiude una frase;
    - il segmento supera `max_seconds` (taglio forzato).
    """
    speakers = assign_speakers(words, turns or [])
    segments: list[BuiltSegment] = []
    current: BuiltSegment | None = None
    for word, speaker in zip(words, speakers, strict=True):
        text, start, end = word[0], float(word[1]), float(word[2])
        if not text.strip():
            continue
        if current is not None:
            prev = current.words[-1]
            duration = end - current.start
            ends_sentence = prev[0].rstrip().endswith(_SENTENCE_END)
            if (
                speaker != current.speaker
                or start - float(prev[2]) > pause_seconds
                or (duration > target_seconds and ends_sentence)
                or duration > max_seconds
            ):
                segments.append(current)
                current = None
        if current is None:
            current = BuiltSegment(start=start, end=end, speaker=speaker)
        current.words.append(word)
        current.end = max(current.end, end)
    if current is not None:
        segments.append(current)
    return segments
