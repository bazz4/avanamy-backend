# src/avanamy/repositories/generation_job_repository.py

from sqlalchemy.orm import Session
from avanamy.models.generation_job import GenerationJob

class GenerationJobRepository:

    @staticmethod
    def create(db: Session, *, api_spec_id: int, job_type: str,
               status: str = "pending", output_metadata: dict | None = None):

        job = GenerationJob(
            api_spec_id=api_spec_id,
            job_type=job_type,
            status=status,
            output_metadata=output_metadata,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    @staticmethod
    def get_by_id(db: Session, job_id: int) -> GenerationJob | None:
        return db.query(GenerationJob).filter(GenerationJob.id == job_id).first()

    @staticmethod
    def list_for_spec(db: Session, api_spec_id: int):
        return (
            db.query(GenerationJob)
            .filter(GenerationJob.api_spec_id == api_spec_id)
            .order_by(GenerationJob.created_at.desc())
            .all()
        )

    @staticmethod
    def update_status(db: Session, job_id: int, new_status: str):
        job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
        if not job:
            return None
        job.status = new_status
        db.commit()
        db.refresh(job)
        return job
