import os
from typing import Optional, List, Dict, Any
from qdrant_client import QdrantClient
from qdrant_client.http import models as qdrant_models
from sentence_transformers import SentenceTransformer

QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))

qdrant_client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

# Modello per embeddings vettoriali (384 dimensioni)
embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

COLLECTION_NAME = "interview_chunks"

def init_vector_db():
    """Crea la collezione su Qdrant se non esiste già."""
    try:
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
            print(f"✅ Collection '{COLLECTION_NAME}' creata con successo su Qdrant.")
    except Exception as e:
        print(f"❌ Errore durante l'inizializzazione di Qdrant: {e}")

def add_transcription_to_qdrant(interview_id: int, filename: str, segments: list):
    """
    Riceve i segmenti della trascrizione, li vettorializza e li salva su Qdrant.
    """    
    init_vector_db() 
    
    if not segments:
        return

    points = []
    
    for idx, seg in enumerate(segments):
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

        vector = embedding_model.encode(text).tolist()

        payload = {
            "interview_id": interview_id,
            "filename": filename,
            "segment_index": idx,
            "start": float(start),
            "end": float(end),
            "text": text.strip()
        }

        point_id = (interview_id * 10000) + idx

        points.append(
            qdrant_models.PointStruct(
                id=point_id,
                vector=vector,
                payload=payload
            )
        )
    
    if points:
        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=points
        )

def search_transcriptions(query: str, limit: int = 5, interview_id: Optional[int] = None) -> List[Dict[str, Any]]:    
    """
    Esegue una ricerca semantica su Qdrant.
    """
    if not query.strip():
        return []

    init_vector_db() 

    query_vector = embedding_model.encode(query).tolist()

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
    
    try:
        search_result = qdrant_client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_vector,
            query_filter=query_filter,
            limit=limit
        ).points
    except Exception as e:
        print(f"⚠️ Errore durante la query su Qdrant: {e}")
        return []
    
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