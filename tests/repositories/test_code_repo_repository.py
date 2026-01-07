import uuid

from avanamy.repositories.code_repo_repository import CodeRepoRepository
from avanamy.models.code_repository import CodeRepository


def test_create_code_repository(db):
    repo = CodeRepoRepository.create(
        db,
        tenant_id="tenant-1",
        name="Repo",
        url="https://github.com/org/repo.git",
    )

    assert repo.tenant_id == "tenant-1"
    assert repo.scan_status == "pending"


def test_get_by_id(db):
    repo = CodeRepoRepository.create(
        db,
        tenant_id="tenant-1",
        name="Repo",
        url="https://github.com/org/repo.git",
    )

    fetched = CodeRepoRepository.get_by_id(db, repo.id)
    assert fetched.id == repo.id


def test_get_by_tenant(db):
    CodeRepoRepository.create(
        db,
        tenant_id="tenant-1",
        name="Repo1",
        url="https://github.com/org/repo1.git",
    )
    CodeRepoRepository.create(
        db,
        tenant_id="tenant-2",
        name="Repo2",
        url="https://github.com/org/repo2.git",
    )

    repos = CodeRepoRepository.get_by_tenant(db, "tenant-1")
    assert len(repos) == 1
    assert repos[0].name == "Repo1"


def test_update_repository(db):
    repo = CodeRepoRepository.create(
        db,
        tenant_id="tenant-1",
        name="Repo",
        url="https://github.com/org/repo.git",
    )

    updated = CodeRepoRepository.update(db, repo, owner_team="Team")
    assert updated.owner_team == "Team"


def test_delete_repository(db):
    repo = CodeRepoRepository.create(
        db,
        tenant_id="tenant-1",
        name="Repo",
        url="https://github.com/org/repo.git",
    )

    CodeRepoRepository.delete(db, repo)
    assert db.query(CodeRepository).filter(CodeRepository.id == repo.id).first() is None
