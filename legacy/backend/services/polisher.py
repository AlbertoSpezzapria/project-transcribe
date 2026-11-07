import os
from typing import List, Dict, Any
import instructor
from openai import OpenAI
from schemas import PolishedTranscriptionResponse, PolishedSegment
from services.system_prompts import SYSTEM_PROMPT_POLISHER

raw_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

client = instructor.from_openai(raw_client)

def _polish_batch(segments_batch: List[Dict[str, Any]], model_name: str) -> PolishedTranscriptionResponse:
    """Esegue il polishing su un singolo blocco di segmenti."""
    formatted_input = ""
    for seg in segments_batch:
        formatted_input += f"[{seg['start']:.1f}s - {seg['end']:.1f}s]: {seg['text']}\n"

    user_prompt = f"""Ecco un blocco di trascrizione grezza divisa per timestamp:

{formatted_input}

Riscrivi e pulisci il testo applicando le regole editoriali.
Restituisci la sintesi del blocco, i temi chiave e il testo segmento per segmento.
"""

    return client.chat.completions.create(
        model=model_name,
        response_model=PolishedTranscriptionResponse,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_POLISHER},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2,
        max_retries=2
    )

def polish_transcription(
    raw_segments: List[Dict[str, Any]], 
    model_name: str = None,
    batch_size: int = 35  # Circa 35 segmenti (~2-3 min di parlato) per chiamata
) -> PolishedTranscriptionResponse:
    """
    Raffina trascrizioni audio di qualsiasi lunghezza dividendo i segmenti in batch
    per evitare che l'LLM superi il limite massimo di output tokens (truncation).
    """
    if not model_name:
        model_name = os.getenv("DEFAULT_LLM_MODEL", "openai/gpt-4o-mini")

    # Se l'intervista è breve, esegui una sola chiamata
    if len(raw_segments) <= batch_size:
        return _polish_batch(raw_segments, model_name)

    # Per interviste lunghe, processa a blocchi
    all_polished_segments: List[PolishedSegment] = []
    summaries: List[str] = []
    all_key_topics: List[str] = []

    for i in range(0, len(raw_segments), batch_size):
        batch = raw_segments[i:i + batch_size]
        try:
            res = _polish_batch(batch, model_name)
            all_polished_segments.extend(res.segments)
            if res.summary:
                summaries.append(res.summary)
            if res.key_topics:
                all_key_topics.extend(res.key_topics)
        except Exception as e:
            print(f"Errore durante il polishing del batch {i}: {e}")
            # Fallback per il batch in caso di errore: mantiene i segmenti grezzi
            for seg in batch:
                all_polished_segments.append(
                    PolishedSegment(
                        start=seg.get("start", 0.0),
                        end=seg.get("end", 0.0),
                        raw_text=seg.get("text", ""),
                        polished_text=seg.get("text", "")
                    )
                )

    # Deduplica i tag/topics mantenendo l'ordine
    unique_topics = list(dict.fromkeys(all_key_topics))
    
    # Unifica la trascrizione completa e genera un riassunto finale sintetico
    full_polished_text = "\n\n".join([s.polished_text for s in all_polished_segments if s.polished_text])
    unified_summary = " ".join(summaries)

    return PolishedTranscriptionResponse(
        summary=unified_summary,
        key_topics=unique_topics,
        polished_full_text=full_polished_text,
        segments=all_polished_segments
    )