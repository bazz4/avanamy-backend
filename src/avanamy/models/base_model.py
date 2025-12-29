"""Standard column definitions for consistency."""
from sqlalchemy import Column, ForeignKey, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from sqlalchemy.types import DateTime

def uuid_pk():
    return Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("uuid_generate_v4()"),
        nullable=False
    )

def uuid_fk(table: str, nullable: bool = False, ondelete: str = "CASCADE"):
    return Column(
        UUID(as_uuid=True),
        ForeignKey(f"{table}.id", ondelete=ondelete),
        nullable=nullable,
        index=True
    )

def timestamp_created():
    return Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False
    )

def timestamp_updated():
    return Column(
        DateTime(timezone=True),
        onupdate=func.now()
    )