"""Riconoscimento del tipo di file dal contenuto (non dall'estensione)."""

from dataclasses import dataclass

import filetype

from app.models import SourceType

AUDIO = {
    "audio/mpeg",
    "audio/mp4",
    "audio/x-m4a",
    "audio/m4a",
    "audio/wav",
    "audio/x-wav",
    "audio/ogg",
    "audio/flac",
    "audio/x-flac",
    "audio/aac",
    "audio/webm",
    "audio/amr",
}
VIDEO = {"video/mp4", "video/quicktime", "video/webm", "video/x-matroska", "video/x-m4v"}
DOCUMENT = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.oasis.opendocument.text",
    "application/rtf",
}
TEXT_EXTENSIONS = {".txt", ".md"}


@dataclass
class Detected:
    mime: str
    source_type: SourceType


class UnsupportedFile(Exception):
    pass


def detect(head: bytes, filename: str, declared_mime: str | None) -> Detected:
    kind = filetype.guess(head)
    declared = (declared_mime or "").split(";")[0].strip().lower()

    if kind is None:
        # File di testo semplice: nessuna "firma" binaria, verifichiamo che sia UTF-8.
        if any(filename.lower().endswith(ext) for ext in TEXT_EXTENSIONS):
            try:
                head.decode("utf-8")
            except UnicodeDecodeError as exc:
                # l'ultimo carattere può essere spezzato a metà dal taglio dei byte
                if exc.start < len(head) - 4:
                    raise UnsupportedFile("Il file di testo deve essere in UTF-8") from exc
            return Detected("text/plain", SourceType.document)
        raise UnsupportedFile("Tipo di file non riconosciuto")

    mime = kind.mime
    # Le registrazioni dal browser (webm/ogg/mp4) sono contenitori che `filetype`
    # riconosce come video: se il client dichiara audio, le trattiamo come audio.
    if mime in VIDEO and declared.startswith("audio/"):
        return Detected(declared if declared in AUDIO else "audio/webm", SourceType.audio)
    if mime == "video/mp4" and filename.lower().endswith(".m4a"):
        return Detected("audio/mp4", SourceType.audio)
    if mime in AUDIO:
        return Detected(mime, SourceType.audio)
    if mime in VIDEO:
        return Detected(mime, SourceType.video)
    if mime in DOCUMENT:
        return Detected(mime, SourceType.document)
    raise UnsupportedFile(f"Formato non supportato: {mime}")
