# tests/conftest.py
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from avanamy.db.database import Base

# IMPORTANT: Import all models so SQLAlchemy registers the tables
import avanamy.models.api_spec
import avanamy.models.generation_job
import avanamy.models.documentation_artifact
import avanamy.models.version_history

@pytest.fixture(autouse=True)
def clean_db(engine):
    """Automatically truncate all tables before each test."""
    # Drop & recreate all tables
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

@pytest.fixture(scope="session")
def engine():
    """Create in-memory SQLite DB with all tables."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )

    # Must be after importing models!
    Base.metadata.create_all(engine)

    yield engine

    Base.metadata.drop_all(engine)


@pytest.fixture()
def db(engine):
    """Return a new SQLAlchemy session for each test."""
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
