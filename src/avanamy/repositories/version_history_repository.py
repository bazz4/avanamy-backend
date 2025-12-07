from typing import Any

from sqlalchemy.orm import Session
from avanamy.models.api_spec import ApiSpec
from avanamy.models.version_history import VersionHistory
import logging
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class VersionHistoryRepository:
    @staticmethod
    def create(
        db: Session,
        *,
        api_spec_id: int,
        diff: dict[str, Any] | None = None,
        changelog: str | None = None,
    ) -> VersionHistory:
        """
        Create a new version history record for an API spec.

        - Automatically increments `version` for this api_spec_id.
        - `diff` can be None for now; we'll start populating it once we wire in diffing.
        """

        with tracer.start_as_current_span("db.create_version_history") as span:
            span.set_attribute("api_spec_id", api_spec_id)

            # Find the current latest version for this spec
            last_version = (
                db.query(VersionHistory)
                .filter(VersionHistory.api_spec_id == api_spec_id)
                .order_by(VersionHistory.version.desc())
                .first()
            )

            next_version = (last_version.version + 1) if last_version else 1

            span.set_attribute("version.next", next_version)

            version_row = VersionHistory(
                api_spec_id=api_spec_id,
                version=next_version,
                diff=diff,
                changelog=changelog,
            )

            db.add(version_row)
            db.commit()
            db.refresh(version_row)

        logger.info(
            "Created version history id=%s version=%s for spec=%s",
            getattr(version_row, "id", "?"),
            version_row.version,
            api_spec_id,
        )

        return version_row

    @staticmethod
    def list_for_spec(db: Session, api_spec_id: int) -> list[VersionHistory]:
        """
        Return versions for a given spec, newest first.
        """

        with tracer.start_as_current_span("db.list_version_history") as span:
            span.set_attribute("api_spec_id", api_spec_id)

            results = (
                db.query(VersionHistory)
                .filter(VersionHistory.api_spec_id == api_spec_id)
                .order_by(VersionHistory.created_at.desc())
                .all()
            )

        logger.debug(
            "Listed %d versions for spec=%s",
            len(results),
            api_spec_id,
        )

        return results
    
    @staticmethod
    def next_version_for_spec(db: Session, api_spec_id: int) -> str:
        """
        Return the next version label (e.g., 'v1', 'v2', ...) for a given spec_id.
        This is purely a label. The numeric VersionHistory.version is still
        auto-managed in create().
        """
        with tracer.start_as_current_span("db.next_version_for_spec") as span:
            span.set_attribute("api_spec_id", api_spec_id)

            count = (
                db.query(VersionHistory)
                .filter(VersionHistory.api_spec_id == api_spec_id)
                .count()
            )

        next_label = f"v{count + 1}"
        logger.debug(
            "Next version label for spec=%s is %s",
            api_spec_id,
            next_label,
        )
        return next_label
