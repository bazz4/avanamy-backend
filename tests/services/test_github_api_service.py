import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock, AsyncMock

from github import GithubException

from avanamy.services.github_api_service import GitHubAPIService


@pytest.mark.anyio
async def test_list_repositories_success(monkeypatch):
    class DummyResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "repositories": [
                    {
                        "name": "repo",
                        "full_name": "org/repo",
                        "clone_url": "https://github.com/org/repo.git",
                        "default_branch": "main",
                        "private": True,
                    }
                ]
            }

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, _url, headers=None):
            return DummyResponse()

    monkeypatch.setattr(
        "avanamy.services.github_app_service.GitHubAppService.get_installation_token",
        AsyncMock(return_value="token"),
    )
    monkeypatch.setattr("httpx.AsyncClient", DummyClient)

    service = GitHubAPIService("token")
    repos = await service.list_repositories(installation_id=123)

    assert repos == [
        {
            "name": "repo",
            "full_name": "org/repo",
            "clone_url": "https://github.com/org/repo.git",
            "default_branch": "main",
            "private": True,
        }
    ]


@pytest.mark.anyio
async def test_list_repositories_error(monkeypatch):
    class DummyResponse:
        def raise_for_status(self):
            raise RuntimeError("boom")

        def json(self):
            return {}

    class DummyClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def get(self, _url, headers=None):
            return DummyResponse()

    monkeypatch.setattr(
        "avanamy.services.github_app_service.GitHubAppService.get_installation_token",
        AsyncMock(return_value="token"),
    )
    monkeypatch.setattr("httpx.AsyncClient", DummyClient)

    service = GitHubAPIService("token")
    with pytest.raises(ValueError):
        await service.list_repositories(installation_id=123)


def test_clone_repository_auth_url(monkeypatch, tmp_path):
    repo_obj = SimpleNamespace(head=SimpleNamespace(commit=SimpleNamespace(hexsha="abc123")))

    clone_mock = MagicMock(return_value=repo_obj)
    monkeypatch.setattr("avanamy.services.github_api_service.Repo.clone_from", clone_mock)

    service = GitHubAPIService("token123")
    repo_path, commit_sha = service.clone_repository(
        "https://github.com/org/repo.git",
        str(tmp_path),
    )

    assert repo_path == str(tmp_path)
    assert commit_sha == "abc123"

    called_url = clone_mock.call_args.args[0]
    assert "x-access-token:token123@github.com" in called_url


def test_clone_repository_error(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "avanamy.services.github_api_service.Repo.clone_from",
        MagicMock(side_effect=Exception("boom")),
    )

    service = GitHubAPIService("token123")
    with pytest.raises(ValueError):
        service.clone_repository("https://github.com/org/repo.git", str(tmp_path))


def test_verify_access(monkeypatch):
    github = SimpleNamespace(get_repo=MagicMock(return_value=SimpleNamespace(name="repo")))
    monkeypatch.setattr(
        "avanamy.services.github_api_service.Github",
        MagicMock(return_value=github),
    )

    service = GitHubAPIService("token")
    assert service.verify_access("org/repo") is True


def test_verify_access_failure(monkeypatch):
    github = SimpleNamespace(get_repo=MagicMock(side_effect=GithubException(404, "nope", None)))
    monkeypatch.setattr(
        "avanamy.services.github_api_service.Github",
        MagicMock(return_value=github),
    )

    service = GitHubAPIService("token")
    assert service.verify_access("org/repo") is False
