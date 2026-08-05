import io
from faster_whisper import WhisperModel

# Inizializzazione del modello (mantieni la tua configurazione esistente, es. cpu/cuda, float32/int8)
model = WhisperModel("base", device="cpu", compute_type="int8")

def transcribe_audio(file_path: str):
    """
    Legge il file audio dal disco come byte stream prima di passarlo a Whisper
    per evitare errori di sistema operativo [Errno 22] nei container Docker.
    """
    print(f"Avvio trascrizione per il file: {file_path}...")

    # 1. Carica l'intero contenuto del file in memoria come un buffer BinaryIO
    with open(file_path, "rb") as f:
        audio_bytes = io.BytesIO(f.read())

    # 2. Passa il buffer di memoria al modello Whisper anziché il percorso stringa
    segments, info = model.transcribe(
        audio_bytes,
        beam_size=5,
        language="it" # opzionale, oppure auto-detect
    )

    # 3. Trasforma il generatore in una lista
    segments_list = list(segments)
    
    # 4. Ricostruisci la trascrizione completa
    transcript_text = " ".join([seg.text.strip() for seg in segments_list])

    return segments_list, transcript_text