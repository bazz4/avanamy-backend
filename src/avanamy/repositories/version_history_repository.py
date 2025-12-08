# src/avanamy/repositories/version_history_repository.py
from typing import Any, Optional

from sqlalchemy.orm import Session
from avanamy.models.version_history import VersionHistory
import logging
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class VersionHistoryRepository:
    @staticmethod
    def _get_latest_row(db: Session, api_spec_id: int) -> Optional[VersionHistory]:
        return (
            db.query(VersionHistory)
            .filter(VersionHistory.api_spec_id == api_spec_id)
            .order_by(VersionHistory.version.desc())
            .first()
        )

    @staticmethod
    def get_latest_version_number(db: Session, api_spec_id: int) -> Optional[int]:
        """
        Return the latest numeric version for a given spec, or None if no history yet.
        """
        with tracer.start_as_current_span("db.get_latest_version_number") as span:
            span.set_attribute("api_spec_id", api_spec_id)
            last = VersionHistoryRepository._get_latest_row(db, api_spec_id)
            return last.version if last else None

    @staticmethod
    def next_version_number(db: Session, api_spec_id: int) -> int:
        """
        Return the *next* version number (1, 2, 3, ...) for a given spec.
        """
        latest = VersionHistoryRepository.get_latest_version_number(db, api_spec_id)
        return (latest or 0) + 1

    @staticmethod
    def latest_version_label(db: Session, api_spec_id: int) -> Optional[str]:
        """
        Return a label like 'v1', 'v2', ... for the *latest* version of this spec.
        Returns None if there is no history.
        """
        latest = VersionHistoryRepository.get_latest_version_number(db, api_spec_id)
        if latest is None:
            return None
        return f"v{latest}"

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

            next_version = VersionHistoryRepository.next_version_number(db, api_spec_id)
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

    # Optional: backward-compatible alias if old code still expects it
    @staticmethod
    def next_version_for_spec(db: Session, api_spec_id: int) -> str:
        """
        Historically used as 'next version label'; we now keep it as an alias
        to avoid breaking imports, but it returns the *next* label, not the latest.
        Prefer using latest_version_label() for writing docs.
        """
        with tracer.start_as_current_span("db.next_version_for_spec") as span:
            span.set_attribute("api_spec_id", api_spec_id)
            next_num = VersionHistoryRepository.next_version_number(db, api_spec_id)
        label = f"v{next_num}"
        logger.debug("Next version label for spec=%s is %s", api_spec_id, label)
        return label

    @staticmethod
    def current_version_label_for_spec(db: Session, api_spec_id: int) -> str:
        """
        Return the *current* version label for a spec (e.g., 'v1', 'v2').
        If there is no version history yet, default to 'v1'.
        """
        last_version = (
            db.query(VersionHistory)
            .filter(VersionHistory.api_spec_id == api_spec_id)
            .order_by(VersionHistory.version.desc())
            .first()
        )

        if not last_version:
            return "v1"

        return f"v{last_version.version}"
