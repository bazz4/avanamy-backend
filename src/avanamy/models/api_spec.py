from sqlalchemy import Column, Integer, String, Text, JSON, DateTime
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from avanamy.db.database import Base

class ApiSpec(Base):
    __tablename__ = "api_specs"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    version = Column(String, nullable=True)
    description = Column(Text, nullable=True)

    original_file_s3_path = Column(String, nullable=False)
    parsed_schema = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
