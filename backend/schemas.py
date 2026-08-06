from pydantic import BaseModel, Field
from typing import List, Optional, Any
from datetime import datetime

class PolishedSegment(BaseModel):
    start: float = Field(..., description="Timestamp di inizio in secondi")
    end: float = Field(..., description="Timestamp di fine in secondi")
    polished_text: str = Field(..., description="Testo pulito ed editoriale di questo segmento")

class PolishedTranscriptionResponse(BaseModel):
    summary: str = Field(..., description="Breve sintesi di 2-3 frasi del contenuto")
    key_topics: List[str] = Field(..., description="Lista dei temi principali emersi")
    segments: List[PolishedSegment] = Field(..., description="Lista dei singoli segmenti raffinati")

# Schema compatto per la lista delle interviste
class InterviewSummaryResponse(BaseModel):
    id: int
    filename: str
    status: str
    summary: Optional[str] = None
    key_topics: Optional[List[str]] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

# Schema dettagliato per la singola intervista
class InterviewDetailResponse(BaseModel):
    id: int
    filename: str
    file_path: Optional[str] = None
    status: str
    summary: Optional[str] = None
    key_topics: Optional[List[str]] = None
    raw_transcript: Optional[str] = None
    raw_segments: Optional[List[Any]] = None
    polished_transcript: Optional[str] = None
    polished_segments: Optional[List[Any]] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ChatRequest(BaseModel):
    question: str = Field(..., description="La domanda dell'utente sulle interviste")
    interview_id: Optional[int] = Field(None, description="ID specifico per interrogare una sola intervista. Se null, cerca su tutto l'archivio.")
    limit: int = Field(default=5, ge=1, le=15, description="Numero massimo di chunk di contesto da recuperare")

class SourceSegment(BaseModel):
    interview_id: int
    filename: str
    start: float
    end: float
    text: str

class ChatResponse(BaseModel):
    answer: str = Field(..., description="La risposta dettagliata elaborata dall'LLM")
    sources: List[SourceSegment] = Field(..., description="I segmenti esatti usati come fonte con i timestamp per la citazione")