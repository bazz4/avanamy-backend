import pytest
from unittest.mock import patch
import uuid
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.orm import Session

from avanamy.models.api_product import ApiProduct
from avanamy.models.provider import Provider
from avanamy.models.tenant import Tenant
from avanamy.services.api_product_delete_service import delete_api_product_fully
from avanamy.models.api_spec import ApiSpec
from avanamy.models.version_history import VersionHistory
from avanamy.models.watched_api import WatchedAPI
from avanamy.models.alert_configuration import AlertConfiguration
from avanamy.db.database import Base


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

def test_delete_api_product_deletes_s3_objects(db_session: Session):
    """
    Ensure deleting an API product deletes ALL S3 objects under its prefix.
    This test prevents silent S3 no-op deletes.
    """

    tenant_id = "tenant_test"
    product_id = str(uuid.uuid4())

    tenant = Tenant(
        id=tenant_id,
        slug="test-tenant",
    )

    provider = Provider(
        id=str(uuid.uuid4()),
        slug="test-provider",
        tenant_id=tenant_id,
    )

    product = ApiProduct(
        id=product_id,
        tenant_id=tenant_id,
        provider_id=provider.id,
        slug="test-product",
        name="Test Product",
    )

    db_session.add_all([tenant, provider, product])
    db_session.commit()

    fake_s3_objects = [
        {"Key": "tenants/test-tenant/providers/test-provider/api_products/test-product/versions/v1/spec.json"},
        {"Key": "tenants/test-tenant/providers/test-provider/api_products/test-product/versions/v1/docs.html"},
    ]

    with patch("avanamy.services.s3.boto3.client") as mock_boto_client:
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Mock paginator
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {"Contents": fake_s3_objects}
        ]
        mock_s3.get_paginator.return_value = mock_paginator

        # Execute delete
        delete_api_product_fully(
            db=db_session,
            tenant_id=tenant_id,
            api_product_id=product_id,
        )

        # Assert delete_objects was called correctly
        mock_s3.delete_objects.assert_called_once()

        args, kwargs = mock_s3.delete_objects.call_args

        assert kwargs["Bucket"] is not None
        assert "Delete" in kwargs
        assert len(kwargs["Delete"]["Objects"]) == 2

        deleted_keys = {obj["Key"] for obj in kwargs["Delete"]["Objects"]}

        assert deleted_keys == {
            obj["Key"] for obj in fake_s3_objects
        }
