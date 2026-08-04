from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# to modify when using docker
SQLALCHEMY_DATABASE_URL = "postgresql+psycopg://myuser:mypassword@localhost:5433/interviewdb"

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()