# src/avanamy/models/code_repository.py

"""
Code Repository models for code scanning and impact analysis.
"""

from __future__ import annotations
from datetime import datetime, timezone
from uuid import UUID, uuid4
from sqlalchemy import String, Text, DateTime, ForeignKey, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from avanamy.db.database import Base


class CodeRepository(Base):
    """
    A connected code repository (GitHub, GitLab, etc.)
    Used for scanning code to find API endpoint usage.
    """
    
    __tablename__ = "code_repositories"
    
    # Primary key
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    
    # Tenant isolation
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    
    # Repository info
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)  # e.g., https://github.com/org/repo
    
    # Authentication (encrypted in production)
    github_installation_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Ownership (for impact alerts)
    owner_team: Mapped[str | None] = mapped_column(String(255), nullable=True)
    owner_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    
    # Scan status
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_scan_commit_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    scan_status: Mapped[str] = mapped_column(
        String(20), 
        nullable=False, 
        default="pending"
    )  # pending, scanning, success, failed
    last_scan_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # Stats
    total_files_scanned: Mapped[int] = mapped_column(default=0)
    total_endpoints_found: Mapped[int] = mapped_column(default=0)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    
    # Relationships
    endpoint_usages: Mapped[list["CodeRepoEndpointUsage"]] = relationship(
        back_populates="code_repository",
        cascade="all, delete-orphan"
    )
    
    # Indexes
    __table_args__ = (
        Index("ix_code_repositories_tenant_id", "tenant_id"),
        Index("ix_code_repositories_scan_status", "scan_status"),
    )
    
    def __repr__(self) -> str:
        return f"<CodeRepository(id={self.id}, name={self.name}, tenant={self.tenant_id})>"


class CodeRepoEndpointUsage(Base):
    """
    Records where an API endpoint is used in a code repository.
    This powers impact analysis.
    """
    
    __tablename__ = "code_repo_endpoint_usages"
    
    # Primary key
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    
    # Foreign keys
    code_repository_id: Mapped[UUID] = mapped_column(ForeignKey("code_repositories.id", ondelete="CASCADE"), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    
    # Endpoint identification
    endpoint_path: Mapped[str] = mapped_column(String(500), nullable=False)  # e.g., /v1/users
    http_method: Mapped[str | None] = mapped_column(String(10), nullable=True)  # GET, POST, etc.
    
    # Location in code
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)  # relative to repo root
    line_number: Mapped[int] = mapped_column(nullable=False)
    code_context: Mapped[str | None] = mapped_column(Text, nullable=True)  # The actual line of code
    
    # Detection metadata
    detection_method: Mapped[str] = mapped_column(
        String(20), 
        nullable=False, 
        default="regex"
    )  # regex, ast, manual
    confidence: Mapped[float] = mapped_column(nullable=False, default=1.0)  # 0.0 to 1.0
    
    # Scan metadata
    commit_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=lambda: datetime.now(timezone.utc)
    )
    
    # Relationships
    code_repository: Mapped["CodeRepository"] = relationship(back_populates="endpoint_usages")
    
    # Indexes
    __table_args__ = (
        Index("ix_code_repo_endpoint_usages_tenant_id", "tenant_id"),
        Index("ix_code_repo_endpoint_usages_code_repository_id", "code_repository_id"),
        Index("ix_code_repo_endpoint_usages_endpoint_path", "endpoint_path"),
        Index("ix_code_repo_endpoint_usages_lookup", "tenant_id", "endpoint_path", "http_method"),
    )
    
    def __repr__(self) -> str:
        return f"<CodeRepoEndpointUsage(repo={self.code_repository_id}, endpoint={self.http_method} {self.endpoint_path})>"