import uuid
from datetime import datetime, timezone, timedelta
from types import SimpleNamespace

from unittest.mock import AsyncMock


def _repo(tenant_id="tenant_test123", **kwargs):
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=kwargs.get("id", uuid.uuid4()),
        tenant_id=tenant_id,
        name=kwargs.get("name", "Repo"),
        url=kwargs.get("url", "https://github.com/org/repo.git"),
        owner_team=kwargs.get("owner_team"),
        owner_email=kwargs.get("owner_email"),
        scan_status=kwargs.get("scan_status", "pending"),
        last_scanned_at=None,
        last_scan_commit_sha=None,
        last_scan_error=None,
        total_files_scanned=0,
        total_endpoints_found=0,
        scan_interval_hours=kwargs.get("scan_interval_hours", 24),
        next_scan_at=kwargs.get("next_scan_at", now + timedelta(hours=24)),
        consecutive_scan_failures=kwargs.get("consecutive_scan_failures", 0),
        created_at=now,
        updated_at=now,
        endpoint_usages=kwargs.get("endpoint_usages", []),
        access_token_encrypted=kwargs.get("access_token_encrypted"),
        github_installation_id=kwargs.get("github_installation_id"),
    )


def test_create_code_repository(client, monkeypatch):
    repo = _repo()
    monkeypatch.setattr(
        "avanamy.api.routes.code_repositories.CodeRepoRepository.create",
        lambda *_args, **_kwargs: repo,
    )

    resp = client.post(
        "/code-repositories",
        json={
            "name": "Repo",
            "url": "https://github.com/org/repo.git",
        },
    )

    assert resp.status_code == 201
    data = resp.json()
    assert data["tenant_id"] == "tenant_test123"
    assert data["scan_status"] == "pending"


def test_list_code_repositories_filters_tenant(client, monkeypatch):
    monkeypatch.setattr(
        "avanamy.api.routes.code_repositories.CodeRepoRepository.get_by_tenant",
        lambda _db, tenant_id: [_repo(tenant_id=tenant_id, name="Repo1")],
    )

    resp = client.get("/code-repositories")
    assert resp.status_code == 200
    data = resp.json()

    assert len(data) == 1
    assert data[0]["name"] == "Repo1"


def test_get_code_repository_includes_usages(client, monkeypatch):
    repo = _repo(
        endpoint_usages=[
            SimpleNamespace(
                endpoint_path="/v1/users",
                http_method="GET",
                file_path="app.py",
                line_number=10,
                code_context="fetch('/v1/users')",
                detection_method="regex",
                confidence=0.9,
            )
        ]
    )
    monkeypatch.setattr(
        "avanamy.api.routes.code_repositories.CodeRepoRepository.get_by_id",
        lambda _db, _id: repo,
    )

    resp = client.get(f"/code-repositories/{repo.id}")
    assert resp.status_code == 200
    data = resp.json()

    assert data["endpoint_usages"][0]["endpoint_path"] == "/v1/users"


def test_get_code_repository_forbidden(client, monkeypatch):
    repo = _repo(tenant_id="other-tenant")
    monkeypatch.setattr(
        "avanamy.api.routes.code_repositories.CodeRepoRepository.get_by_id",
        lambda _db, _id: repo,
    )

    resp = client.get(f"/code-repositories/{repo.id}")
    assert resp.status_code == 403


def test_update_code_repository(client, monkeypatch):
    repo = _repo()
    monkeypatch.setattr(
        "avanamy.api.routes.code_repositories.CodeRepoRepository.get_by_id",
        lambda _db, _id: repo,
    )
    monkeypatch.setattr(
        "avanamy.api.routes.code_repositories.CodeRepoRepository.update",
        lambda _db, _repo, **updates: _repo.__class__(**{**_repo.__dict__, **updates}),
    )

    resp = client.put(
        f"/code-repositories/{repo.id}",
        json={"owner_team": "Team A"},
    )

    assert resp.status_code == 200
    assert resp.json()["owner_team"] == "Team A"


def test_delete_code_repository(client, monkeypatch):
    repo = _repo()
    monkeypatch.setattr(
        "avanamy.api.routes.code_repositories.CodeRepoRepository.get_by_id",
        lambda _db, _id: repo,
    )
    monkeypatch.setattr(
        "avanamy.api.routes.code_repositories.CodeRepoRepository.delete",
        lambda *_args, **_kwargs: None,
    )

    resp = client.delete(f"/code-repositories/{repo.id}")
    assert resp.status_code == 204


def test_connect_github_stores_token(client, monkeypatch):
    repo = _repo(access_token_encrypted=None)
    updated = _repo(access_token_encrypted="encrypted")

    monkeypatch.setattr(
        "avanamy.api.routes.code_repositories.CodeRepoRepository.get_by_id",
        lambda _db, _id: repo,
    )
    monkeypatch.setattr(
        "avanamy.api.routes.code_repositories.CodeRepoRepository.update",
        lambda _db, _repo, **_kw: updated,
    )

    resp = client.post(
        f"/code-repositories/{repo.id}/connect-github",
        json={"access_token_encrypted": "encrypted"},
    )
    assert resp.status_code == 200
    assert resp.json()["tenant_id"] == "tenant_test123"


def test_trigger_scan_requires_token(client, monkeypatch):
    repo = _repo(github_installation_id=None)
    monkeypatch.setattr(
        "avanamy.api.routes.code_repositories.CodeRepoRepository.get_by_id",
        lambda _db, _id: repo,
    )

    resp = client.post(f"/code-repositories/{repo.id}/scan")
    assert resp.status_code == 400


def test_trigger_scan_success(client, monkeypatch):
    repo = _repo(github_installation_id=123)
    monkeypatch.setattr(
        "avanamy.api.routes.code_repositories.CodeRepoRepository.get_by_id",
        lambda _db, _id: repo,
    )
    monkeypatch.setattr(
        "avanamy.api.routes.code_repositories.CodeRepoRepository.update",
        lambda *_args, **_kwargs: repo,
    )

    class DummyScanner:
        def __init__(self, _):
            pass

        async def scan_repository_from_github(self, **_):
            return {"status": "success"}

    monkeypatch.setattr(
        "avanamy.services.code_repo_scanner_service.CodeRepoScannerService",
        DummyScanner,
    )
    monkeypatch.setattr(
        "avanamy.services.github_app_service.GitHubAppService.get_installation_token",
        AsyncMock(return_value="token"),
    )

    resp = client.post(f"/code-repositories/{repo.id}/scan")
    assert resp.status_code == 202
    assert resp.json()["status"] == "pending"
