import pytest
from unittest.mock import patch

from avanamy.services.api_product_delete_service import delete_api_product_fully
from avanamy.models.api_product import ApiProduct
from avanamy.models.api_spec import ApiSpec
from avanamy.models.version_history import VersionHistory
from avanamy.models.watched_api import WatchedAPI
from avanamy.models.alert_configuration import AlertConfiguration


def test_delete_api_product_fully_deletes_all_related_data(db_session, tenant, provider):
    """
    GIVEN an API product with specs, versions, watched APIs, and alerts
    WHEN delete_api_product_fully is called
    THEN all related DB records are removed
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

    spec = ApiSpec(
        tenant_id=tenant.id,
        api_product_id=product.id,
        provider_id=provider.id,
        name="test-api.yaml",
    )
    db_session.add(spec)
    db_session.commit()

    vh = VersionHistory(
        api_spec_id=spec.id,
        version=1,
        changelog="Initial",
    )
    db_session.add(vh)

    watched = WatchedAPI(
        tenant_id=tenant.id,
        api_product_id=product.id,
        provider_id=provider.id,
        spec_url="https://example.com/openapi.yaml",
    )
    db_session.add(watched)
    db_session.commit()

    alert = AlertConfiguration(
        watched_api_id=watched.id,
        enabled=True,
    )
    db_session.add(alert)
    db_session.commit()

    # --- Act ---
    with patch("avanamy.services.api_product_delete_service.delete_s3_prefix") as mock_s3:
        delete_api_product_fully(
            db=db_session,
            tenant_id=tenant.id,
            api_product_id=product.id,
        )

    # --- Assert ---
    assert db_session.query(ApiProduct).count() == 0
    assert db_session.query(ApiSpec).count() == 0
    assert db_session.query(VersionHistory).count() == 0
    assert db_session.query(WatchedAPI).count() == 0
    assert db_session.query(AlertConfiguration).count() == 0

    mock_s3.assert_called_once()
