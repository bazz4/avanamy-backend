"""
Mixins for SQLAlchemy models.
Provides reusable column sets for audit trails, timestamps, etc.
"""
from sqlalchemy import Column, String, DateTime
from sqlalchemy.sql import func


class AuditMixin:
    """
    Adds audit columns to any model.
    
    Provides:
    - created_at: Automatic timestamp (UTC) when record is created
    - updated_at: Automatic timestamp (UTC) when record is modified
    - created_by_user_id: Clerk user_id of creator
    - updated_by_user_id: Clerk user_id of last updater
    
    Usage:
        class MyModel(Base, AuditMixin):
            __tablename__ = "my_table"
            id = Column(UUID, primary_key=True)
            # created_at, updated_at, etc. are inherited automatically
    """
    
    created_at = Column(
        DateTime(timezone=True), 
        server_default=func.now(), 
        nullable=False,
        comment="UTC timestamp when record was created"
    )
    
    updated_at = Column(
        DateTime(timezone=True), 
        onupdate=func.now(),
        comment="UTC timestamp when record was last updated"
    )
    
    created_by_user_id = Column(
        String(255),
        comment="Clerk user_id of user who created this record"
    )
    
    updated_by_user_id = Column(
        String(255),
        comment="Clerk user_id of user who last updated this record"
    )