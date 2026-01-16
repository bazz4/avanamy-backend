# tests/conftest.py
import pytest
import uuid

from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles

from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
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
import avanamy.models.code_repository
import avanamy.models.organization_member
import avanamy.models.organization_invitation


@compiles(JSONB, "sqlite")
def _compile_jsonb_for_sqlite(type_, compiler, **kw):
    # SQLite doesn't support JSONB; compile to JSON for test databases.
    return "JSON"


@pytest.fixture(scope="session")
def engine():
    """Create an in-memory SQLite database shared across tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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
    from avanamy.auth.clerk import get_current_tenant_id, get_current_user_id

    app.dependency_overrides[db_get_db] = override_get_db
    async def override_get_current_user_id():
        return "user_test123"

    app.dependency_overrides[get_current_tenant_id] = override_auth
    app.dependency_overrides[get_current_user_id] = override_get_current_user_id

    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def db_session(db):
    """Compatibility fixture for tests expecting db_session."""
    return db


@pytest.fixture
def tenant(db):
    """Standalone tenant fixture for tests that don't use tenant_provider_product."""
    from avanamy.models.tenant import Tenant

    tenant = Tenant(
        id="tenant_fixture",
        name="Fixture Tenant",
        slug="tenant-fixture",
        is_organization=False,
    )
    db.add(tenant)
    db.commit()
    db.refresh(tenant)
    return tenant


@pytest.fixture
def provider(db, tenant):
    """Standalone provider fixture for tests that don't use tenant_provider_product."""
    from avanamy.models.provider import Provider

    provider = Provider(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="Fixture Provider",
        slug="provider-fixture",
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return provider
