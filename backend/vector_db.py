import os
from typing import Optional, List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from sentence_transformers import SentenceTransformer

# Recupera la configurazione dell'host di Qdrant dalle variabili d'ambiente
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))

qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

# Modello per embeddings vettoriali (384 dimensioni)
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

COLLECTION_NAME = "interview_chunks"

def init_vector_db():
    """Crea la collezione su Qdrant se non esiste già."""
    collections = qdrant_client.get_collections().collections
    exists = any(col.name == COLLECTION_NAME for col in collections)
    
    if not exists:
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=qdrant_models.VectorParams(
                size=384,  # Dimensione dei vettori per all-MiniLM-L6-v2
                distance=qdrant_models.Distance.COSINE
            )
        )

def add_transcription_to_qdrant(interview_id: int, filename: str, segments: list):
    """
    Riceve i segmenti della trascrizione (grezzi o puliti), li vettorializza
    e li salva su Qdrant in batch.
    """    
    points = []
    
    for idx, seg in enumerate(segments):
        # 1. Recupero dinamico del testo (compatibile sia con dict che con oggetti Pydantic/Whisper)
        if isinstance(seg, dict):
            text = seg.get("polished_text") or seg.get("text", "")
            start = seg.get("start", 0.0)
            end = seg.get("end", 0.0)
        else:
            text = getattr(seg, "polished_text", getattr(seg, "text", ""))
            start = getattr(seg, "start", 0.0)
            end = getattr(seg, "end", 0.0)

        if not text or not text.strip():
            continue

        # 2. Generazione dell'embedding
        vector = embedding_model.encode(text).tolist()

        # 3. Creazione del payload dei metadati
        payload = {
            "interview_id": interview_id,
            "filename": filename,
            "segment_index": idx,
            "start": float(start),
            "end": float(end),
            "text": text.strip()
        }

        # 4. Generazione ID unico per il punto (es. 10000 + idx per evitare collisioni)
        point_id = (interview_id * 10000) + idx

        # 5. Aggiunta alla lista dei punti per l'upsert
        points.append(
            qdrant_models.PointStruct(
                id=point_id,
                vector=vector,
                payload=payload
            )
        )
    
    # 6. Carica i punti in batch su Qdrant se la lista non è vuota
    if points:
        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=points
        )

def search_transcriptions(query: str, limit: int = 5, interview_id: Optional[int] = None) -> List[Dict[str, Any]]:    
    """
    Esegue una ricerca semantica su Qdrant usando la query dell'utente
    ed eventualmente filtrando per interview_id.
    """
    if not query.strip():
        return []

    # 1. Vettorializza la query dell'utente
    query_vector = embedding_model.encode(query).tolist()

    # 2. Costruzione del filtro opzionale per interview_id
    query_filter = None
    if interview_id:
        query_filter = qdrant_models.Filter(
            must=[
                qdrant_models.FieldCondition(
                    key="interview_id",
                    match=qdrant_models.MatchValue(value=interview_id)
                )
            ]
        )
    
    # 3. Esegue la ricerca vettoriale passando il filtro
    search_result = qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=query_vector,
        query_filter=query_filter,  # <-- Inserito il filtro mancante
        limit=limit
    ).points
    
    # 4. Formatta i risultati estraendo il payload e il punteggio di similarità
    results = []
    for hit in search_result:
        results.append({
            "score": hit.score,
            "interview_id": hit.payload.get("interview_id"),
            "filename": hit.payload.get("filename"),
            "start": hit.payload.get("start"),
            "end": hit.payload.get("end"),
            "text": hit.payload.get("text")
        })
        
    return results