import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from avanamy.services.code_repo_scanner_service import CodeRepoScannerService
from avanamy.services.code_scanner import EndpointMatch
from avanamy.models.code_repository import CodeRepository, CodeRepoEndpointUsage


class DummyScanner:
    def __init__(self, matches):
        self._matches = matches

    def supports_language(self, file_extension: str) -> bool:
        return file_extension == ".py"

    def scan_file(self, file_path: str, file_content: str):
        return list(self._matches)


@pytest.mark.anyio
async def test_scan_repository_success(tmp_path):
    repo_id = uuid4()
    repo = SimpleNamespace(
        id=repo_id,
        tenant_id="tenant-1",
        scan_status="pending",
        last_scan_commit_sha=None,
        last_scan_error=None,
        total_files_scanned=0,
        total_endpoints_found=0,
    )

    query_repo = MagicMock()
    query_repo.filter.return_value.first.return_value = repo

    query_usage = MagicMock()
    query_usage.filter.return_value.delete.return_value = 0

    db = MagicMock()
    db.query.side_effect = lambda model: query_repo if model is CodeRepository else query_usage

    file_path = tmp_path / "app.py"
    file_path.write_text("print('hello')", encoding="utf-8")
    (tmp_path / "ignore.txt").write_text("nope", encoding="utf-8")

    matches = [
        EndpointMatch(
            endpoint_path="/v1/users",
            http_method="GET",
            file_path="app.py",
            line_number=1,
            code_context="fetch('/v1/users')",
            confidence=1.0,
            detection_method="regex",
        )
    ]

    service = CodeRepoScannerService(db, scanner=DummyScanner(matches))
    result = await service.scan_repository(repo_id, str(tmp_path), "sha123")

    assert result["files_scanned"] == 1
    assert result["endpoints_found"] == 1
    assert repo.scan_status == "success"
    assert db.add.call_count == 1


@pytest.mark.anyio
async def test_scan_repository_missing_repo():
    db = MagicMock()
    query_repo = MagicMock()
    query_repo.filter.return_value.first.return_value = None
    db.query.return_value = query_repo

    service = CodeRepoScannerService(db)
    with pytest.raises(ValueError):
        await service.scan_repository(uuid4(), "path", "sha")


def test_find_affected_repositories_groups_results():
    usage = SimpleNamespace(
        code_repository_id=uuid4(),
        code_repository=SimpleNamespace(name="Repo", owner_team="Team", owner_email="a@b.com"),
        file_path="app.py",
        line_number=10,
        code_context="fetch('/v1/users')",
        http_method="GET",
        confidence=0.9,
    )

    query = MagicMock()
    query.filter.return_value = query
    query.all.return_value = [usage]

    db = MagicMock()
    db.query.return_value = query

    service = CodeRepoScannerService(db)
    result = service.find_affected_repositories("tenant-1", "/v1/users", "GET")

    assert result[0]["code_repository_name"] == "Repo"
    assert result[0]["usages"][0]["file_path"] == "app.py"


@pytest.mark.anyio
async def test_scan_repository_from_github_invokes_scan(monkeypatch):
    repo_id = uuid4()
    repo = SimpleNamespace(
        id=repo_id,
        tenant_id="tenant-1",
        url="https://github.com/org/repo.git",
        scan_status="pending",
        last_scan_error=None,
    )

    query_repo = MagicMock()
    query_repo.filter.return_value.first.return_value = repo

    db = MagicMock()
    db.query.return_value = query_repo

    service = CodeRepoScannerService(db)

    fake_scan = AsyncMock(return_value={"status": "success"})
    monkeypatch.setattr(service, "scan_repository", fake_scan)

    class DummyGitHubService:
        def __init__(self, *_):
            pass

        def clone_repository(self, _repo_url, target_dir):
            return target_dir, "sha123"

    monkeypatch.setattr(
        "avanamy.services.github_api_service.GitHubAPIService",
        DummyGitHubService,
    )

    result = await service.scan_repository_from_github(repo_id, "token")

    assert result["status"] == "success"
    fake_scan.assert_awaited_once()
