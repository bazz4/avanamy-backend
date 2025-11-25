from avanamy.repositories.api_spec_repository import ApiSpecRepository
from avanamy.repositories.generation_job_repository import GenerationJobRepository


def test_create_generation_job(db):
    spec = ApiSpecRepository.create(db, name="Spec", original_file_s3_path="s3://x")

    job = GenerationJobRepository.create(
        db,
        api_spec_id=spec.id,
        job_type="documentation",
    )

    assert job.id is not None
    assert job.status == "pending"
    assert job.api_spec_id == spec.id


def test_update_job_status(db):
    spec = ApiSpecRepository.create(db, name="Spec", original_file_s3_path="s3://x")
    job = GenerationJobRepository.create(db, api_spec_id=spec.id, job_type="doc")

    updated = GenerationJobRepository.update_status(db, job.id, "running")
    assert updated.status == "running"


def test_list_jobs_for_spec(db):
    spec = ApiSpecRepository.create(db, name="Spec", original_file_s3_path="s3://x")

    GenerationJobRepository.create(db, api_spec_id=spec.id, job_type="doc")
    GenerationJobRepository.create(db, api_spec_id=spec.id, job_type="doc")

    jobs = GenerationJobRepository.list_for_spec(db, spec.id)
    assert len(jobs) == 2
