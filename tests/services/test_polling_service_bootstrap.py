import pytest
from unittest.mock import AsyncMock, patch

from avanamy.services.polling_service import PollingService
from avanamy.models.watched_api import WatchedAPI
from avanamy.models.api_product import ApiProduct
from avanamy.models.version_history import VersionHistory


@pytest.mark.asyncio
async def test_first_poll_creates_single_version(db_session, tenant, provider):
    """
    GIVEN a watched API with no existing ApiSpec
    WHEN poll_watched_api is called
    THEN exactly one VersionHistory row is created (v1)
    """

    # --- Arrange ---
    product = ApiProduct(
        tenant_id=tenant.id,
        provider_id=provider.id,
        name="Test Product",
        slug="test-product",
    )
    db_session.add(product)
    db_session.commit()

    watched_api = WatchedAPI(
        tenant_id=tenant.id,
        provider_id=provider.id,
        api_product_id=product.id,
        spec_url="https://example.com/openapi.yaml",
        polling_enabled=True,
    )
    db_session.add(watched_api)
    db_session.commit()

    service = PollingService(db_session)

    # Mock external fetch
    with patch.object(
        PollingService,
        "_fetch_spec",
        AsyncMock(return_value="openapi: 3.0.0\ninfo:\n  title: Test\n"),
    ):
        result = await service.poll_watched_api(watched_api.id)

    # --- Assert ---
    versions = db_session.query(VersionHistory).all()

    assert len(versions) == 1
    assert versions[0].version == 1
    assert result["status"] == "success"
    assert db_session.query(VersionHistory).count() == 1

