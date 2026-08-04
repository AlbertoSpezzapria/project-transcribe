import os
import shutil
from fastapi import FastAPI, File, UploadFile, Depends, HTTPException
from sqlalchemy.orm import Session
from database import engine, Base, get_db
from models import Interview

# Create the tables in the database and the upload folder
Base.metadata.create_all(bind=engine)
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="Interview AI Platform")

@app.post("/upload")
async def upload_audio(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # Check extension
    if not file.filename.endswith(('.m4a', '.mp3', '.wav')):
        raise HTTPException(status_code=400, detail="Formato non supportato")

    file_path = os.path.join(UPLOAD_DIR, file.filename)

    # Save file to disk
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Create record in the database
    new_interview = Interview(
        filename=file.filename,
        file_path=file_path,
        status="uploaded"
    )
    db.add(new_interview)
    db.commit()
    db.refresh(new_interview)

    return {
        "message": "Upload successful",
        "interview_id": new_interview.id,
        "status": new_interview.status
    }