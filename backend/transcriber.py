from faster_whisper import WhisperModel

# Choose the model size ("tiny", "base", "small", "medium")
MODEL_SIZE = "base"

model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")

def transcribe_audio(file_path: str):
    """
    Esegue la trascrizione dell'audio e restituisce sia la lista dei segmenti 
    grezzi (per il DB vettoriale) sia il testo completo formattato (per il DB relazionale).
    """
    print(f"Avvio trascrizione per il file: {file_path}...")

    # segments è un generatore, lo convertiamo in lista per poterlo riutilizzare
    segments_gen, info = model.transcribe(file_path, beam_size=5, language="it")
    segments_list = list(segments_gen)

    print(f"Lingua rilevata: {info.language} con probabilità {info.language_probability}")

    full_transcript = []
    for segment in segments_list:
        line = f"[{segment.start:.2f}s -> {segment.end:.2f}s]: {segment.text}"
        full_transcript.append(line)
        print(line)

    transcript_text = "\n".join(full_transcript)

    # Restituisce entrambi: la lista dei segmenti e la stringa unita
    return segments_list, transcript_text