from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime
from database import Base

class Interview(Base):
    __tablename__ = "interviews"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    file_path = Column(String)
    status = Column(String, default="uploaded")
    transcript = Column(Text, nullable=True)  
    created_at = Column(DateTime, default=datetime.utcnow)
