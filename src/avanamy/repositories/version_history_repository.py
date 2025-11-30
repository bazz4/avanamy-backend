# src/avanamy/repositories/version_history_repository.py

from sqlalchemy.orm import Session
from avanamy.models.version_history import VersionHistory
import logging
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class VersionHistoryRepository:

    @staticmethod
    def create(db: Session, *, api_spec_id: int,
               version_label: str, changelog: str | None = None):

        version = VersionHistory(
            api_spec_id=api_spec_id,
            version_label=version_label,
            changelog=changelog,
        )
        with tracer.start_as_current_span("db.create_version_history") as span:
            span.set_attribute("api_spec_id", api_spec_id)
            span.set_attribute("version.label", version_label)
            db.add(version)
            db.commit()
            db.refresh(version)

        logger.info("Created version %s for spec=%s", version_label, api_spec_id)
        return version

    @staticmethod
    def list_for_spec(db: Session, api_spec_id: int):
        with tracer.start_as_current_span("db.list_version_history") as span:
            span.set_attribute("api_spec_id", api_spec_id)
            results = (
                db.query(VersionHistory)
                .filter(VersionHistory.api_spec_id == api_spec_id)
                .order_by(VersionHistory.created_at.desc())
                .all()
            )

        logger.debug("Listed %d versions for spec=%s", len(results), api_spec_id)
        return results
