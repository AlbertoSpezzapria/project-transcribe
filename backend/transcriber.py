from faster_whisper import WhisperModel

# Choose the model size ("tiny", "base", "small", "medium")
MODEL_SIZE = "base"

model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")

def transcribe_audio(file_path: str) -> str:
    """
    Execute the transcription of an audio file and return the complete text.
    """
    print(f"Avvio trascrizione per il file: {file_path}...")

    # segments is a generator that yields pieces of text as they are processed
    segments, info = model.transcribe(file_path, beam_size=5, language="it")

    print(detect_language_info := f"Lingua rilevata: {info.language} con probabilità {info.language_probability}")

    full_transcript = []
    for segment in segments:
        # Each segment contains text and timestamps (start, end) which are very useful for future audio player integration
        line = f"[{segment.start:.2f}s -> {segment.end:.2f}s]: {segment.text}"
        full_transcript.append(line)
        print(line)

    return "\n".join(full_transcript)