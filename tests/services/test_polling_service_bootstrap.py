import pytest
from unittest.mock import AsyncMock, patch

from avanamy.services.polling_service import PollingService
from avanamy.models.watched_api import WatchedAPI
from avanamy.models.api_product import ApiProduct
from avanamy.models.version_history import VersionHistory


@pytest.mark.anyio
async def test_first_poll_creates_single_version(db_session, tenant, provider, monkeypatch):
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

    async def _fake_store_api_spec_file(
        db,
        file_bytes,
        filename,
        tenant_id,
        api_product_id,
        provider_id,
        **_,
    ):
        from uuid import UUID
        from avanamy.models.api_spec import ApiSpec
        from avanamy.models.version_history import VersionHistory

        spec = ApiSpec(
            tenant_id=tenant_id,
            api_product_id=UUID(str(api_product_id)),
            provider_id=UUID(str(provider_id)),
            name=filename,
            original_file_s3_path="s3://bucket/bootstrap.yaml",
            version="v1",
        )
        db.add(spec)
        db.commit()
        db.refresh(spec)

        vh = VersionHistory(
            api_spec_id=spec.id,
            version=1,
            changelog="Initial upload",
        )
        db.add(vh)
        db.commit()
        return spec

    monkeypatch.setattr(
        "avanamy.services.api_spec_service.store_api_spec_file",
        _fake_store_api_spec_file,
    )

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

