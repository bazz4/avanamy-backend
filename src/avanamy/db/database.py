from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import NullPool
from pydantic import BaseModel
import os

# ---------------------------------------------------------
# Configure the database URL (loads from environment variable)
# ---------------------------------------------------------
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg2://avanamy:avanamy_password@localhost:5432/avanamy_dev",
)

# ---------------------------------------------------------
# SQLAlchemy Base class
# ---------------------------------------------------------
class Base(DeclarativeBase):
    pass

# ---------------------------------------------------------
# Create engine
# ---------------------------------------------------------
# NullPool prevents connection reuse issues during local dev / hot reload.
engine = create_engine(
    DATABASE_URL,
    poolclass=NullPool,
    echo=False,  # set True to log SQL
)

# ---------------------------------------------------------
# SessionLocal factory
# ---------------------------------------------------------
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

# ---------------------------------------------------------
# FastAPI dependency
# ---------------------------------------------------------
def get_db():
    """Yields a database session for each request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
