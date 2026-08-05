import os
import shutil
import re
from fastapi import FastAPI, File, UploadFile, Depends, HTTPException
from sqlalchemy.orm import Session
from database import engine, Base, get_db
from models import Interview
from transcriber import transcribe_audio
from vector_db import add_transcription_to_qdrant, search_transcriptions
from services.polisher import polish_transcription

Base.metadata.create_all(bind=engine)
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="Interview AI Platform")

@app.post("/upload")
async def upload_and_transcribe(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(('.m4a', '.mp3', '.wav', '.mp4', '.mpeg')):
        raise HTTPException(status_code=400, detail="Formato audio non supportato")

    # 1. Sanitizza il nome del file (sostituisce spazi e caratteri speciali non standard)
    safe_filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', file.filename)
    file_path = os.path.join(UPLOAD_DIR, safe_filename)

    # 2. Salva il file usando un blocco try/finally per garantire la chiusura del file
    try:
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    finally:
        await file.close()  # Chiude in modo sicuro lo stream di UploadFile di FastAPI

    # 3. Crea il record nel DB con il nome sicuro e lo stato "processing"
    new_interview = Interview(
        filename=file.filename, # Manteniamo il nome originale per la UI
        file_path=file_path,
        status="processing"
    )
    db.add(new_interview)
    db.commit()
    db.refresh(new_interview)

    try:
        # 4. Esegue la trascrizione AI con Whisper sul file_path sanitizzato
        segments_list, raw_transcript_text = transcribe_audio(file_path)
        
        # Prepara la struttura dati dei segmenti grezzi per la chiamata al polisher e per Postgres
        raw_segments_data = [
            {"start": seg.start, "end": seg.end, "text": seg.text}
            for seg in segments_list
        ]

        # Salva la versione grezza (Verbatim) su Postgres
        new_interview.raw_transcript = raw_transcript_text
        new_interview.raw_segments = raw_segments_data
        db.commit()

        # 5. POLISHING AI: Trasforma il testo grezzo in versione editoriale tramite LLM
        # Fallback di default: usiamo i segmenti grezzi per Qdrant
        segments_for_qdrant = raw_segments_data

        try:
            # Invoca il polisher che restituisce l'oggetto Pydantic
            polished_data = polish_transcription(raw_segments_data)
            
            # Assembla la trascrizione pulita completa concatenando i segmenti
            full_polished_text = "\n\n".join([seg.polished_text for seg in polished_data.segments if seg.polished_text])

            # Popola i nuovi campi AI ed editoriali su Postgres
            new_interview.polished_transcript = full_polished_text
            new_interview.polished_segments = [seg.model_dump() for seg in polished_data.segments]
            new_interview.summary = polished_data.summary
            new_interview.key_topics = polished_data.key_topics
            new_interview.status = "completed"
            db.commit()

            # Passa i segmenti puliti a Qdrant
            if polished_data.segments:
                segments_for_qdrant = [
                    {"start": seg.start, "end": seg.end, "text": seg.polished_text}
                    for seg in polished_data.segments
                ]

        except Exception as polish_err:
            print(f"Attenzione: Errore durante il Polishing AI: {polish_err}")
            new_interview.status = "completed_raw_only"
            db.commit()

        # 6. Indicizzazione vettoriale su Qdrant
        try:
            add_transcription_to_qdrant(
                interview_id=new_interview.id,
                filename=file.filename,
                segments=segments_for_qdrant
            )
        except Exception as qdrant_err:
            print(f"Attenzione: Errore durante l'indicizzazione su Qdrant: {qdrant_err}")

    except Exception as e:
        new_interview.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Errore durante la trascrizione AI: {str(e)}")

    return {
        "message": "Intervista caricata, trascritta, raffinata e indicizzata con successo",
        "interview_id": new_interview.id,
        "status": new_interview.status,
        "summary": getattr(new_interview, "summary", None),
        "key_topics": getattr(new_interview, "key_topics", None),
        "raw_preview": raw_transcript_text[:200] + "...",
        "polished_preview": (new_interview.polished_transcript[:200] + "...") if new_interview.polished_transcript else None
    }

@app.get("/search")
async def semantic_search(q: str, limit: int = 5):
    """
    Cerca all'interno di tutte le trascrizioni indicizzate usando la ricerca semantica.
    Esempio: /search?q=parola chiave o argomento&limit=3
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="La query di ricerca non può essere vuota.")
    
    try:
        results = search_transcriptions(query=q, limit=limit)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore durante la ricerca semantica: {str(e)}")
        
    return {
        "query": q,
        "results_count": len(results),
        "results": results
    }