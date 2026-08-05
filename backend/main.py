import os
import shutil
from fastapi import FastAPI, File, UploadFile, Depends, HTTPException
from sqlalchemy.orm import Session
from database import engine, Base, get_db
from models import Interview
from transcriber import transcribe_audio

Base.metadata.create_all(bind=engine)
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="Interview AI Platform")

@app.post("/upload")
async def upload_and_transcribe(file: UploadFile = File(...), db: Session = Depends(get_db)):
    if not file.filename.endswith(('.m4a', '.mp3', '.wav', '.mp4', '.mpeg')):
        raise HTTPException(status_code=400, detail="Formato audio non supportato")

    file_path = os.path.join(UPLOAD_DIR, file.filename)

    # 1. Salva il file su disco
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # 2. Crea il record nel DB con stato "processing"
    new_interview = Interview(
        filename=file.filename,
        file_path=file_path,
        status="processing"
    )
    db.add(new_interview)
    db.commit()
    db.refresh(new_interview)

    try:
        # 3. Esegue la trascrizione AI
        transcript_text = transcribe_audio(file_path)
        
        # 4. Aggiorna il record con il testo e lo stato completato
        new_interview.transcript = transcript_text
        new_interview.status = "completed"
        db.commit()
    except Exception as e:
        new_interview.status = "failed"
        db.commit()
        raise HTTPException(status_code=500, detail=f"Errore durante la trascrizione AI: {str(e)}")

    return {
        "message": "Intervista caricata e trascritta con successo",
        "interview_id": new_interview.id,
        "status": new_interview.status,
        "transcript_preview": transcript_text[:300] + "..." # Mostra un'anteprima
    }