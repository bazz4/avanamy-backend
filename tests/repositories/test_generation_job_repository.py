from types import SimpleNamespace
from unittest.mock import MagicMock

from avanamy.repositories.generation_job_repository import GenerationJobRepository


def test_create_generation_job_commits():
    fake_db = MagicMock()
    fake_db.add = MagicMock()
    fake_db.commit = MagicMock()
    fake_db.refresh = MagicMock()

    job = GenerationJobRepository.create(
        fake_db,
        tenant_id="tenant-1",
        api_spec_id="spec-1",
        job_type="documentation",
    )

    fake_db.add.assert_called_once()
    fake_db.commit.assert_called_once()
    fake_db.refresh.assert_called_once_with(job)
    assert job.status == "pending"
    assert job.job_type == "documentation"


def test_update_job_status_returns_none_if_missing():
    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.first.return_value = None
    assert GenerationJobRepository.update_status(fake_db, 1, "tenant-1", "done") is None


def test_update_job_status_sets_status():
    fake_db = MagicMock()
    job = SimpleNamespace(id=1, status="pending")
    fake_db.query.return_value.filter.return_value.first.return_value = job

    updated = GenerationJobRepository.update_status(fake_db, 1, "tenant-1", "running")
    assert updated.status == "running"
    fake_db.commit.assert_called_once()
    fake_db.refresh.assert_called_once_with(job)


def test_list_jobs_for_spec():
    fake_db = MagicMock()
    fake_db.query.return_value.filter.return_value.order_by.return_value.all.return_value = ["j1", "j2"]
    jobs = GenerationJobRepository.list_for_spec(fake_db, "spec-1", "tenant-1")
    assert jobs == ["j1", "j2"]
