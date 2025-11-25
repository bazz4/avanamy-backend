# src/avanamy/repositories/version_history_repository.py

from sqlalchemy.orm import Session
from avanamy.models.version_history import VersionHistory

class VersionHistoryRepository:

    @staticmethod
    def create(db: Session, *, api_spec_id: int,
               version_label: str, changelog: str | None = None):

        version = VersionHistory(
            api_spec_id=api_spec_id,
            version_label=version_label,
            changelog=changelog,
        )
        db.add(version)
        db.commit()
        db.refresh(version)
        return version

    @staticmethod
    def list_for_spec(db: Session, api_spec_id: int):
        return (
            db.query(VersionHistory)
            .filter(VersionHistory.api_spec_id == api_spec_id)
            .order_by(VersionHistory.created_at.desc())
            .all()
        )
