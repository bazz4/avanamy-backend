from .database import Base
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import String, Integer, Text, ForeignKey, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ----------------------------------------
# API Spec model
# ----------------------------------------
class ApiSpec(Base):
    __tablename__ = "api_specs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    version: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    original_file_s3_path: Mapped[str] = mapped_column(String, nullable=False)
    parsed_schema: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(onupdate=datetime.utcnow)

    generation_jobs: Mapped[List["GenerationJob"]] = relationship(
        back_populates="api_spec",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    documentation_artifacts: Mapped[List["DocumentationArtifact"]] = relationship(
        back_populates="api_spec",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    version_history: Mapped[List["VersionHistory"]] = relationship(
        back_populates="api_spec",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


# ----------------------------------------
# Generation Job model
# ----------------------------------------
class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    api_spec_id: Mapped[int] = mapped_column(
        ForeignKey("api_specs.id", ondelete="CASCADE")
    )
    job_type: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, default="pending", nullable=False)
    output_metadata: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[Optional[datetime]] = mapped_column(onupdate=datetime.utcnow)

    api_spec: Mapped["ApiSpec"] = relationship(back_populates="generation_jobs")


# ----------------------------------------
# Documentation Artifact model
# ----------------------------------------
class DocumentationArtifact(Base):
    __tablename__ = "documentation_artifacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    api_spec_id: Mapped[int] = mapped_column(
        ForeignKey("api_specs.id", ondelete="CASCADE")
    )
    artifact_type: Mapped[str] = mapped_column(String, nullable=False)
    s3_path: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    api_spec: Mapped["ApiSpec"] = relationship(back_populates="documentation_artifacts")


# ----------------------------------------
# Version History model
# ----------------------------------------
class VersionHistory(Base):
    __tablename__ = "version_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    api_spec_id: Mapped[int] = mapped_column(
        ForeignKey("api_specs.id", ondelete="CASCADE")
    )
    version_label: Mapped[str] = mapped_column(String, nullable=False)
    changelog: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    api_spec: Mapped["ApiSpec"] = relationship(back_populates="version_history")
