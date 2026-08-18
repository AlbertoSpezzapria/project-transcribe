import os
import shutil
import re
from fastapi import FastAPI, File, UploadFile, Depends, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import engine, Base, get_db, SessionLocal
from models import Interview
from transcriber import transcribe_audio
from vector_db import add_transcription_to_qdrant, search_transcriptions, init_vector_db
from services.polisher import polish_transcription
from typing import List, Optional
from schemas import InterviewSummaryResponse, InterviewDetailResponse, ChatRequest, ChatResponse, SourceSegment
from services.rag import generate_rag_response
from contextlib import asynccontextmanager
from pydantic import BaseModel
from services.drafter import generate_editorial_draft
from models import Draft

Base.metadata.create_all(bind=engine)
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

class DraftRequest(BaseModel):
    interview_ids: List[int]
    format_type: str  # "article", "newsletter", "linkedin", "qa"
    additional_instructions: Optional[str] = ""

class SaveDraftRequest(BaseModel):
    title: str
    content: str
    format_type: str

def process_interview_background(interview_id: int, file_path: str, filename: str):
    """Esegue la trascrizione Whisper, il Polishing LLM e l'indicizzazione Qdrant in sottofondo."""
    db: Session = SessionLocal()
    try:
        interview = db.query(Interview).filter(Interview.id == interview_id).first()
        if not interview:
            return

        # 1. Trascrizione Whisper AI
        segments_list, raw_transcript_text = transcribe_audio(file_path)
        
        raw_segments_data = [
            {"start": seg.start, "end": seg.end, "text": seg.text}
            for seg in segments_list
        ]

        interview.raw_transcript = raw_transcript_text
        interview.raw_segments = raw_segments_data
        db.commit()

        # 2. Polishing AI tramite LLM
        segments_for_qdrant = raw_segments_data

        try:
            polished_data = polish_transcription(raw_segments_data)
            full_polished_text = "\n\n".join([seg.polished_text for seg in polished_data.segments if seg.polished_text])

            interview.polished_transcript = full_polished_text
            interview.polished_segments = [seg.model_dump() for seg in polished_data.segments]
            interview.summary = polished_data.summary
            interview.key_topics = polished_data.key_topics
            interview.status = "completed"
            db.commit()

            if polished_data.segments:
                segments_for_qdrant = [
                    {
                        "start": seg.start, 
                        "end": seg.end, 
                        "text": seg.polished_text if seg.polished_text else seg.text
                    }
                    for seg in polished_data.segments
                ]

        except Exception as polish_err:
            print(f"Attenzione: Errore durante il Polishing AI per intervista #{interview_id}: {polish_err}")
            interview.status = "completed_raw_only"
            db.commit()

        # 3. Indicizzazione vettoriale su Qdrant
        print(f"📊 [QDRANT] Inizio indicizzazione per Intervista ID {interview.id} con {len(segments_for_qdrant)} segmenti...")
        try:
            add_transcription_to_qdrant(
                interview_id=interview.id,
                filename=filename,
                segments=segments_for_qdrant
            )
            print(f"✅ [QDRANT] Indicizzazione completata con successo per Intervista ID {interview.id}!")
        except Exception as qdrant_err:
            print(f"❌ [QDRANT] Errore durante l'indicizzazione: {qdrant_err}")

    except Exception as e:
        print(f"❌ Errore durante l'elaborazione dell'intervista #{interview_id}: {e}")
        try:
            interview = db.query(Interview).filter(Interview.id == interview_id).first()
            if interview:
                interview.status = "failed"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_vector_db()
    yield

app = FastAPI(title="Interview AI Platform", lifespan=lifespan)

origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

@app.get("/")
async def root():
    """Endpoint di health check per verificare che il server sia attivo."""
    return {
        "status": "online",
        "service": "Interview AI Platform API",
        "docs_url": "/docs"
    }

@app.post("/upload")
async def upload_and_transcribe(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...), 
    db: Session = Depends(get_db)
):
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
        await file.close()

    # 3. Crea il record nel DB con lo stato "processing"
    new_interview = Interview(
        filename=file.filename,
        file_path=file_path,
        status="processing"
    )
    db.add(new_interview)
    db.commit()
    db.refresh(new_interview)

    # 4. Avvia l'elaborazione pesante in sottofondo in modo asincrono
    background_tasks.add_task(
        process_interview_background,
        interview_id=new_interview.id,
        file_path=file_path,
        filename=file.filename
    )

    # 5. Rispondi immediatamente all'utente (< 1 sec)
    return {
        "message": "Intervista caricata con successo. Elaborazione avviata in background.",
        "interview_id": new_interview.id,
        "status": new_interview.status,
        "filename": new_interview.filename
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

# --- GET /interviews (Elenco Completo) ---
@app.get("/interviews", response_model=List[InterviewSummaryResponse])
async def get_all_interviews(
    skip: int = 0, 
    limit: int = 50, 
    db: Session = Depends(get_db)
):
    """
    Restituisce la lista di tutte le interviste caricate nel sistema,
    ordinate per ID decrescente (dalla più recente).
    """
    interviews = (
        db.query(Interview)
        .order_by(Interview.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return interviews

# --- GET /interviews/{interview_id} (Dettaglio Singola Intervista) ---
@app.get("/interviews/{interview_id}", response_model=InterviewDetailResponse)
async def get_interview_by_id(
    interview_id: int, 
    db: Session = Depends(get_db)
):
    """
    Restituisce tutti i dettagli di una singola intervista,
    inclusi la trascrizione grezza, la trascrizione raffinata e i segmenti.
    """
    interview = db.query(Interview).filter(Interview.id == interview_id).first()
    
    if not interview:
        raise HTTPException(
            status_code=404, 
            detail=f"Intervista con ID {interview_id} non trovata"
        )
        
    return interview

@app.delete("/interviews/{interview_id}")
async def delete_interview(
    interview_id: int, 
    db: Session = Depends(get_db)
):
    """
    Elimina un'intervista da Postgres e dal filesystem.
    """
    interview = db.query(Interview).filter(Interview.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Intervista non trovata")

    # Rimuovi il file audio da disco se presente
    if interview.file_path and os.path.exists(interview.file_path):
        try:
            os.remove(interview.file_path)
        except Exception as e:
            print(f"Errore durante la rimozione del file {interview.file_path}: {e}")

    # Rimuovi la voce dal DB
    db.delete(interview)
    db.commit()

    return {"message": f"Intervista {interview_id} eliminata con successo"}

@app.post("/chat", response_model=ChatResponse)
async def chat_with_transcriptions(
    chat_req: ChatRequest,
    db: Session = Depends(get_db)
):
    """
    Interroga il database vettoriale Qdrant recuperando i chunk pertinenti
    e sintetizza una risposta motivata via LLM con citazioni precise dei timestamp.
    """
    # 1. Recupera i segmenti più rilevanti da Qdrant
    try:
        retrieved_chunks = search_transcriptions(
            query=chat_req.question,
            limit=chat_req.limit,
            interview_id=chat_req.interview_id
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Errore durante il recupero dei contesti vettoriali: {str(e)}"
        )

    if not retrieved_chunks:
        return ChatResponse(
            answer="Non ho trovato alcun segmento pertinente nell'archivio per rispondere alla tua domanda.",
            sources=[]
        )

    # 2. Genera la risposta dell'LLM tramite RAG
    try:
        answer_text = generate_rag_response(
            question=chat_req.question,
            context_chunks=retrieved_chunks
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Errore durante la generazione della risposta AI: {str(e)}"
        )

    # 3. Formatta le fonti per la risposta JSON del client
    sources = [
        SourceSegment(
            interview_id=chunk["interview_id"],
            filename=chunk["filename"],
            start=chunk["start"],
            end=chunk["end"],
            text=chunk["text"]
        )
        for chunk in retrieved_chunks
    ]

    return ChatResponse(
        answer=answer_text,
        sources=sources
    )


@app.post("/draft/generate")
async def generate_draft(request: DraftRequest, db: Session = Depends(get_db)):
    if not request.interview_ids:
        raise HTTPException(status_code=400, detail="Seleziona almeno un'intervista.")

    interviews = db.query(Interview).filter(Interview.id.in_(request.interview_ids)).all()
    if not interviews:
        raise HTTPException(status_code=404, detail="Interviste non trovate.")

    # Assembla il contesto
    context_text = ""
    for idx, interview in enumerate(interviews):
        context_text += f"\n\n--- INTERVISTA {idx + 1}: {interview.filename} ---\n"
        context_text += interview.summary or "Nessun riassunto disponibile. Testo:\n" + (interview.polished_transcript[:3000] if interview.polished_transcript else "")

    # Mappatura dei prompt in base al formato richiesto
    format_prompts = {
        "article": "Scrivi un articolo giornalistico di approfondimento in terza persona (titolo, sottotitolo, paragrafi). Usa citazioni dirette se pertinenti.",
        "newsletter": "Scrivi una sintesi breve e accattivante per una newsletter, evidenziando 3 punti chiave (bullet points).",
        "linkedin": "Scrivi un post per LinkedIn professionale, coinvolgente e strutturato con paragrafi brevi. Includi hashtag pertinenti alla fine.",
        "qa": "Struttura il contenuto come un'intervista Botta & Risposta, mettendo le domande in grassetto e le risposte in chiaro."
    }

    base_prompt = format_prompts.get(request.format_type, format_prompts["article"])
    
    system_prompt = (
        "Sei un caporedattore esperto e un copywriter brillante. "
        "Il tuo compito è scrivere una bozza partendo dalle fonti fornite."
    )
    
    user_prompt = f"""
    FORMATO RICHIESTO: {base_prompt}
    ISTRUZIONI AGGIUNTIVE: {request.additional_instructions}
    
    Ecco le fonti a tua disposizione:
    {context_text}
    
    Scrivi ora la bozza completa:
    """

    try:
        # Usa la nuova funzione dedicata per la generazione della bozza
        draft_content = generate_editorial_draft(system_prompt, user_prompt)
        return {"draft": draft_content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Errore nella generazione: {str(e)}")

@app.post("/drafts")
async def save_draft(draft: SaveDraftRequest, db: Session = Depends(get_db)):
    try:
        new_draft = Draft(
            title=draft.title,
            content=draft.content,
            format_type=draft.format_type
        )
        db.add(new_draft)
        db.commit()
        db.refresh(new_draft)
        return {"message": "Bozza salvata con successo", "id": new_draft.id}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Errore nel salvataggio: {str(e)}")