from sqlalchemy.dialects.postgresql import UUID, JSON
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from sqlalchemy.orm import Mapped
from avanamy.models.impact_analysis import ImpactAnalysisResult
from avanamy.db.database import Base
from avanamy.models.base_model import uuid_fk, timestamp_created
from avanamy.models.mixins import AuditMixin

class VersionHistory(Base, AuditMixin):
    __tablename__ = "version_history"

    id = Column(Integer, primary_key=True, index=True)
    api_spec_id = uuid_fk("api_specs", nullable=False)

    version = Column(Integer, nullable=False)
    diff = Column(JSON, nullable=True)
    summary = Column(String, nullable=True)
    changelog = Column(String, nullable=True)

    impact_analyses: Mapped[list[ImpactAnalysisResult]] = relationship(
        "ImpactAnalysisResult",
        back_populates="version_history",
        cascade="all, delete-orphan"
    )

    api_spec = relationship("ApiSpec")