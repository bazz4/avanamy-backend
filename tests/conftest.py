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
import avanamy.models.watched_api
import avanamy.models.alert_configuration
import avanamy.models.alert_history
import avanamy.models.endpoint_health


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

    tenant_id = "tenant_test123"
    provider_id = uuid.uuid4()
    product_id = uuid.uuid4()

    tenant = Tenant(id=tenant_id, name="Test Tenant", slug="test-tenant", is_organization=False)
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
def override_auth():
    """Mock Clerk authentication to return a test tenant ID."""
    async def mock_get_current_tenant_id():
        return "tenant_test123"
    return mock_get_current_tenant_id


@pytest.fixture
def client(db, override_auth):
    """FastAPI test client that routes all DB deps to the test session."""
    def override_get_db():
        try:
            yield db
        finally:
            pass

    # Apply override for get_db dependency used across all routes
    from avanamy.db.database import get_db as db_get_db
    from avanamy.auth.clerk import get_current_tenant_id

    app.dependency_overrides[db_get_db] = override_get_db
    app.dependency_overrides[get_current_tenant_id] = override_auth

    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()
