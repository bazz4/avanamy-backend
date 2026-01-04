# src/avanamy/services/api_product_delete_service.py

import logging
from sqlalchemy.orm import Session

from avanamy.models.api_product import ApiProduct
from avanamy.models.api_spec import ApiSpec
from avanamy.models.version_history import VersionHistory
from avanamy.models.watched_api import WatchedAPI
from avanamy.models.alert_configuration import AlertConfiguration
from avanamy.services.s3 import delete_s3_prefix
from avanamy.models.provider import Provider
from avanamy.models.tenant import Tenant
from avanamy.models.documentation_artifact import DocumentationArtifact


logger = logging.getLogger(__name__)


def delete_api_product_fully(
    *,
    db: Session,
    tenant_id: str,
    api_product_id: str,
):
    """
    HARD delete an API product and all related data + S3 artifacts.
    Intended for dev/test cleanup.
    """

    product = (
        db.query(ApiProduct)
        .filter(
            ApiProduct.id == api_product_id,
            ApiProduct.tenant_id == tenant_id,
        )
        .first()
    )

    if not product:
        raise ValueError("API Product not found")

    provider = db.query(Provider).filter(Provider.id == product.provider_id).first()
    tenant = db.query(Tenant).filter(Tenant.id == product.tenant_id).first()

    logger.warning(
        "Deleting API product %s and ALL related data",
        product.id,
    )

    # -----------------------------
    # Delete Watched APIs + Alerts
    # -----------------------------
    watched_apis = (
        db.query(WatchedAPI)
        .filter(WatchedAPI.api_product_id == product.id)
        .all()
    )

    watched_api_ids = [w.id for w in watched_apis]

    db.query(AlertConfiguration).filter(
        AlertConfiguration.watched_api_id.in_(watched_api_ids)
    ).delete(synchronize_session=False)

    db.query(WatchedAPI).filter(
        WatchedAPI.api_product_id == product.id
    ).delete(synchronize_session=False)

    # -----------------------------
    # Delete ApiSpecs + Versions + Docs
    # -----------------------------
    specs = (
        db.query(ApiSpec)
        .filter(ApiSpec.api_product_id == product.id)
        .all()
    )

    spec_ids = [s.id for s in specs]

    # 1. Delete documentation artifacts FIRST
    version_ids = (
        db.query(VersionHistory.id)
        .filter(VersionHistory.api_spec_id.in_(spec_ids))
        .subquery()
    )

    db.query(DocumentationArtifact).filter(
        DocumentationArtifact.version_history_id.in_(version_ids)
    ).delete(synchronize_session=False)

    # 2. Delete version history
    db.query(VersionHistory).filter(
        VersionHistory.api_spec_id.in_(spec_ids)
    ).delete(synchronize_session=False)

    # 3. Delete specs
    db.query(ApiSpec).filter(
        ApiSpec.id.in_(spec_ids)
    ).delete(synchronize_session=False)


    # -----------------------------
    # Delete S3 artifacts
    # -----------------------------
    if tenant and provider:
        s3_prefix = (
            f"tenants/{tenant.slug}/"
            f"providers/{provider.slug}/"
            f"products/{product.slug}/"
        )

        logger.warning("Deleting S3 prefix: %s", s3_prefix)
        delete_s3_prefix(s3_prefix)

    # -----------------------------
    # Delete ApiProduct
    # -----------------------------
    db.delete(product)
    db.commit()

    logger.warning("API product %s deleted successfully", product.id)
