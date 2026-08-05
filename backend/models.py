from sqlalchemy import Column, Integer, String, Text, DateTime, JSON
from database import Base

class Interview(Base):
    __tablename__ = "interviews"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, nullable=False)
    file_path = Column(String, nullable=True)  
    raw_transcript = Column(Text, nullable=True)         # Testo grezzo concatenato
    raw_segments = Column(JSON, nullable=True)           # Segmenti grezzi di Whisper con timestamp
    
    # NUOVI CAMPI AI POLISHED
    polished_transcript = Column(Text, nullable=True)    # Testo pulito ed editoriale
    polished_segments = Column(JSON, nullable=True)      # Segmenti puliti con timestamp
    summary = Column(Text, nullable=True)                # Sintesi generata dall'LLM
    key_topics = Column(JSON, nullable=True)             # Temi o tag estratti
    
    status = Column(String, default="processing")