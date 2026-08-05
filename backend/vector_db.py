import os
from qdrant_client import QdrantClient
from qdrant_client.http import models
from sentence_transformers import SentenceTransformer

# Recover the Qdrant host from environment variables (set in the compose)
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))

qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

COLLECTION_NAME = "interview_chunks"

def init_vector_db():
    """Crea la collezione su Qdrant se non esiste già."""
    collections = qdrant_client.get_collections().collections
    exists = any(col.name == COLLECTION_NAME for col in collections)
    
    if not exists:
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=384,  # Dimensione dei vettori per all-MiniLM-L6-v2
                distance=models.Distance.COSINE
            )
        )

def add_transcription_to_qdrant(interview_id: int, filename: str, segments: list):
    """
    Riceve i segmenti della trascrizione da Whisper, li vettorializza
    e li salva su Qdrant con i relativi metadati.
    """
    init_vector_db()
    
    points = []
    for idx, segment in enumerate(segments):
        text = segment.text.strip()
        if not text:
            continue
            
        # Genera il vettore del chunk di testo
        vector = embedding_model.encode(text).tolist()
        
        # ID univoco per il punto nel DB vettoriale (può essere un UUID o un intero combinato)
        point_id = int(f"{interview_id}{idx:04d}")
        
        points.append(
            models.PointStruct(
                id=point_id,
                vector=vector,
                payload={
                    "interview_id": interview_id,
                    "filename": filename,
                    "start": segment.start,
                    "end": segment.end,
                    "text": text
                }
            )
        )
    
    # Carica i punti in batch su Qdrant
    if points:
        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=points
        )