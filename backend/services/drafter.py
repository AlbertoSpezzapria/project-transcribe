import os
from openai import OpenAI

def generate_editorial_draft(system_prompt: str, user_prompt: str) -> str:
    """
    Usa il client OpenAI configurato per OpenRouter per generare testo libero.
    """
    raw_client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=os.getenv("OPENROUTER_API_KEY"),
    )

    # Usa il modello specificato nelle variabili d'ambiente, oppure un default
    model_name = os.getenv("DEFAULT_LLM_MODEL", "openai/gpt-4o-mini")

    try:
        response = raw_client.chat.completions.create(
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,  # Temperatura leggermente più alta per favorire creatività editoriale
        )
        
        return response.choices[0].message.content
    except Exception as e:
        print(f"Errore durante la generazione della bozza con OpenRouter: {e}")
        raise