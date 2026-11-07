import os
from typing import List, Dict, Any
from services.system_prompts import SYSTEM_PROMPT_RAG
from openai import OpenAI

raw_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=os.getenv("OPENROUTER_API_KEY"),
)

def generate_rag_response(question: str, context_chunks: List[Dict[str, Any]], model_name: str = None) -> str:
    if not model_name:
        model_name = os.getenv("DEFAULT_LLM_MODEL", "openai/gpt-4o-mini")

    # Formattazione del contesto con timestamp formattati in MM:SS
    formatted_context = ""
    for idx, chunk in enumerate(context_chunks, 1):
        start_min, start_sec = divmod(int(chunk['start']), 60)
        end_min, end_sec = divmod(int(chunk['end']), 60)
        time_str = f"{start_min:02d}:{start_sec:02d} - {end_min:02d}:{end_sec:02d}"
        
        formatted_context += (
            f"--- Fonte [{idx}] (File: {chunk['filename']}, Tempo: {time_str}) ---\n"
            f"{chunk['text']}\n\n"
        )

    user_prompt = f"""CONTESTO DALL'ARCHIVIO DELLE TRASCRIZIONI:
{formatted_context}

DOMANDA DELL'UTENTE:
{question}
"""

    response = raw_client.chat.completions.create(
        model=model_name,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT_RAG},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.3
    )

    return response.choices[0].message.content