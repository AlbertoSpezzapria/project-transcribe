from pydantic import BaseModel, Field
from typing import List

class PolishedSegment(BaseModel):
    start: float = Field(..., description="Timestamp di inizio in secondi")
    end: float = Field(..., description="Timestamp di fine in secondi")
    polished_text: str = Field(..., description="Testo pulito ed editoriale di questo segmento")

class PolishedTranscriptionResponse(BaseModel):
    summary: str = Field(..., description="Breve sintesi di 2-3 frasi del contenuto")
    key_topics: List[str] = Field(..., description="Lista dei temi principali emersi")
    segments: List[PolishedSegment] = Field(..., description="Lista dei singoli segmenti raffinati")