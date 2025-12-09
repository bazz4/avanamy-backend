# tests/conftest.py
import pytest
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from avanamy.main import app
from avanamy.db.database import Base

# Import models so metadata knows about all tables
import avanamy.models.api_spec
import avanamy.models.generation_job
import avanamy.models.documentation_artifact
import avanamy.models.version_history
import avanamy.models.api_product
import avanamy.models.provider
import avanamy.models.tenant
import avanamy.models.user


@pytest.fixture(scope="session")
def engine():
    """Create an in-memory SQLite database shared across tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture(autouse=True)
def clean_db(engine):
    """Reset all tables before each test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


@pytest.fixture()
def db(engine):
    """Return a new SQLAlchemy session for each test."""
    TestingSessionLocal = sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=engine,
    )
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def tenant_provider_product(db):
    """Create a minimal tenant/provider/product trio for integration-style tests."""
    from avanamy.models.tenant import Tenant
    from avanamy.models.provider import Provider
    from avanamy.models.api_product import ApiProduct

    tenant_id = uuid.uuid4()
    provider_id = uuid.uuid4()
    product_id = uuid.uuid4()

    tenant = Tenant(id=tenant_id, name="Test Tenant", slug="test-tenant")
    provider = Provider(
        id=provider_id,
        tenant_id=tenant_id,
        name="Test Provider",
        slug="test-provider",
    )
    product = ApiProduct(
        id=product_id,
        tenant_id=tenant_id,
        provider_id=provider_id,
        name="Test Product",
        slug="test-product",
    )

    db.add_all([tenant, provider, product])
    db.commit()
    return tenant, provider, product


@pytest.fixture
def client(db):
    """FastAPI test client that routes all DB deps to the test session."""
    def override_get_db():
        try:
            yield db
        finally:
            pass

    # Apply overrides for every route module that defines get_db
    from avanamy.api.routes import api_specs, docs, spec_versions, spec_docs, providers, products

    app.dependency_overrides[api_specs.get_db] = override_get_db
    app.dependency_overrides[docs.get_db] = override_get_db
    app.dependency_overrides[spec_versions.get_db] = override_get_db
    app.dependency_overrides[spec_docs.get_db] = override_get_db
    app.dependency_overrides[providers.get_db] = override_get_db
    app.dependency_overrides[products.get_db] = override_get_db

    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()
