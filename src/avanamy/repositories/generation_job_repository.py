# src/avanamy/repositories/generation_job_repository.py

from sqlalchemy.orm import Session
from avanamy.models.generation_job import GenerationJob
import logging
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


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
        with tracer.start_as_current_span("db.create_generation_job") as span:
            span.set_attribute("api_spec_id", api_spec_id)
            span.set_attribute("job.type", job_type)
            db.add(job)
            db.commit()
            db.refresh(job)

        logger.info("Created generation job id=%s for spec=%s", getattr(job, "id", "?"), api_spec_id)
        return job

    @staticmethod
    def get_by_id(db: Session, job_id: int) -> GenerationJob | None:
        with tracer.start_as_current_span("db.get_generation_job") as span:
            span.set_attribute("job.id", job_id)
            result = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()

        logger.debug("Fetched generation job id=%s -> %s", job_id, getattr(result, "id", None))
        return result

    @staticmethod
    def list_for_spec(db: Session, api_spec_id: int):
        with tracer.start_as_current_span("db.list_generation_jobs") as span:
            span.set_attribute("api_spec_id", api_spec_id)
            results = (
                db.query(GenerationJob)
                .filter(GenerationJob.api_spec_id == api_spec_id)
                .order_by(GenerationJob.created_at.desc())
                .all()
            )

        logger.debug("Listed %d generation jobs for spec=%s", len(results), api_spec_id)
        return results

    @staticmethod
    def update_status(db: Session, job_id: int, new_status: str):
        with tracer.start_as_current_span("db.update_generation_job_status") as span:
            span.set_attribute("job.id", job_id)
            span.set_attribute("job.new_status", new_status)
            job = db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
            if not job:
                return None
            job.status = new_status
            db.commit()
            db.refresh(job)

        logger.info("Updated job %s status -> %s", job_id, new_status)
        return job
