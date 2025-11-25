# src/avanamy/repositories/api_spec_repository.py

from sqlalchemy.orm import Session
from avanamy.models.api_spec import ApiSpec

class ApiSpecRepository:

    @staticmethod
    def create(db: Session, *, name: str, version: str = None,
               description: str = None, original_file_s3_path: str = None,
               parsed_schema: dict = None) -> ApiSpec:

        spec = ApiSpec(
            name=name,
            version=version,
            description=description,
            original_file_s3_path=original_file_s3_path,
            parsed_schema=parsed_schema,
        )
        db.add(spec)
        db.commit()
        db.refresh(spec)
        return spec

    @staticmethod
    def get_by_id(db: Session, spec_id: int) -> ApiSpec | None:
        return db.query(ApiSpec).filter(ApiSpec.id == spec_id).first()

    @staticmethod
    def list_all(db: Session):
        return db.query(ApiSpec).order_by(ApiSpec.created_at.desc()).all()

    @staticmethod
    def delete(db: Session, spec_id: int) -> bool:
        spec = db.query(ApiSpec).filter(ApiSpec.id == spec_id).first()
        if not spec:
            return False
        db.delete(spec)
        db.commit()
        return True
