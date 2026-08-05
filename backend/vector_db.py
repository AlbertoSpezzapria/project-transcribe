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
    points = []
    for idx, seg in enumerate(segments):
        # 1. Recupero dinamico del testo (compatibile sia con grezzo che polished)
        if isinstance(seg, dict):
            text = seg.get("polished_text") or seg.get("text", "")
            start = seg.get("start", 0.0)
            end = seg.get("end", 0.0)
        else:
            text = getattr(seg, "polished_text", getattr(seg, "text", ""))
            start = getattr(seg, "start", 0.0)
            end = getattr(seg, "end", 0.0)

        if not text.strip():
            continue

        # 2. Generazione dell'embedding
        vector = embedding_model.encode(text).tolist()

        # 3. Creazione del punto Qdrant
        payload = {
            "interview_id": interview_id,
            "filename": filename,
            "segment_index": idx,
            "start": start,
            "end": end,
            "text": text
        }
    
    # Carica i punti in batch su Qdrant
    if points:
        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=points
        )

def search_transcriptions(query: str, limit: int = 5):
    """
    Esegue una ricerca semantica su Qdrant usando la query di testo.
    """
    # 1. Vettorializza la query dell'utente
    query_vector = embedding_model.encode(query).tolist()
    
    # 2. Cerca i punti più vicini in Qdrant usando query_points (compatibile con le nuove versioni del client)
    search_result = qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        limit=limit
    ).points  # Estraiamo la lista dei punti dal risultato
    
    # 3. Formatta i risultati estraendo il payload e lo score di similarità
    results = []
    for hit in search_result:
        results.append({
            "score": hit.score,  # Più è vicino a 1.0, più è semanticamente rilevante
            "interview_id": hit.payload.get("interview_id"),
            "filename": hit.payload.get("filename"),
            "start": hit.payload.get("start"),
            "end": hit.payload.get("end"),
            "text": hit.payload.get("text")
        })
        
    return results