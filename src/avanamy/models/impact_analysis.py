# src/avanamy/models/impact_analysis.py

"""
Impact Analysis Models

Tracks the impact of API spec changes on code repositories.
"""

from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4, UUID
from sqlalchemy import (
    String, Integer, Boolean, DateTime, Text, ForeignKey, Index
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import TYPE_CHECKING

from avanamy.db.database import Base
from avanamy.models.mixins import AuditMixin

if TYPE_CHECKING:
    from avanamy.models.api_spec import ApiSpec
    from avanamy.models.version_history import VersionHistory
    from avanamy.models.code_repository import CodeRepoEndpointUsage


class ImpactAnalysisResult(Base, AuditMixin):
    """
    Stores the result of analyzing how API changes impact code repositories.
    
    Created automatically when a new spec version with breaking changes is uploaded.
    Provides historical tracking of impact over time.
    """
    __tablename__ = "impact_analysis_results"
    
    # Primary key
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    
    # Tenant isolation
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    # Foreign keys
    spec_id: Mapped[UUID] = mapped_column(ForeignKey("api_specs.id", ondelete="CASCADE"), nullable=False, index=True)
    version_history_id: Mapped[UUID] = mapped_column(ForeignKey("version_history.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Analysis timestamp
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    
    # Aggregate results
    has_impact: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    total_breaking_changes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_affected_repos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_usages_affected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, default="low")  # critical, high, medium, low
    
    # Relationships
    spec: Mapped[ApiSpec] = relationship("ApiSpec", back_populates="impact_analyses")
    version_history: Mapped[VersionHistory] = relationship("VersionHistory", back_populates="impact_analyses")
    affected_usages: Mapped[list[AffectedCodeUsage]] = relationship(
        "AffectedCodeUsage",
        back_populates="impact_analysis",
        cascade="all, delete-orphan"
    )
    
    # Composite index for common queries
    __table_args__ = (
        Index('idx_impact_tenant_spec', 'tenant_id', 'spec_id'),
        Index('idx_impact_version', 'version_history_id'),
        Index('idx_impact_analyzed_at', 'analyzed_at'),
    )


class AffectedCodeUsage(Base, AuditMixin):
    """
    Links a breaking change to a specific code usage.
    
    Denormalizes file/line details for historical context
    (works even if code repo is deleted later).
    """
    __tablename__ = "affected_code_usages"
    
    # Primary key
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    
    # Tenant isolation
    tenant_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    
    # Foreign keys
    impact_analysis_result_id: Mapped[UUID] = mapped_column(
        ForeignKey("impact_analysis_results.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    code_repo_endpoint_usage_id: Mapped[UUID] = mapped_column(
        ForeignKey("code_repo_endpoint_usages.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    # Breaking change details
    breaking_change_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    endpoint_path: Mapped[str] = mapped_column(String(500), nullable=False)
    http_method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)  # critical, high, medium, low
    
    # Denormalized for historical context (in case code repo deleted)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    code_context: Mapped[str] = mapped_column(Text, nullable=False)
    repository_name: Mapped[str] = mapped_column(String(255), nullable=False)
    repository_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    # Relationships
    impact_analysis: Mapped[ImpactAnalysisResult] = relationship("ImpactAnalysisResult", back_populates="affected_usages")
    code_usage: Mapped[CodeRepoEndpointUsage] = relationship("CodeRepoEndpointUsage")
    
    # Composite indexes for common queries
    __table_args__ = (
        Index('idx_affected_impact', 'impact_analysis_result_id'),
        Index('idx_affected_usage', 'code_repo_endpoint_usage_id'),
        Index('idx_affected_tenant_endpoint', 'tenant_id', 'endpoint_path'),
    )