import types

import pytest

from avanamy.api.routes import github_oauth as github_routes


def test_authorize_generates_state(client, monkeypatch):
    github_routes._oauth_states.clear()

    monkeypatch.setattr(
        "avanamy.api.routes.github_oauth.GitHubOAuthService",
        lambda: types.SimpleNamespace(get_authorization_url=lambda state: f"url-{state}"),
    )

    resp = client.get("/api/github/authorize")
    assert resp.status_code == 200

    data = resp.json()
    assert data["authorization_url"].startswith("url-")
    assert data["state"] in github_routes._oauth_states


@pytest.mark.anyio
async def test_callback_success(client, monkeypatch):
    github_routes._oauth_states.clear()
    github_routes._oauth_states["state-1"] = {"tenant_id": "tenant_test123", "created_at": None}

    class DummyOAuth:
        async def exchange_code_for_token(self, _code):
            return "token"

        async def get_user_info(self, _token):
            return {"login": "octo"}

    monkeypatch.setattr(
        "avanamy.api.routes.github_oauth.GitHubOAuthService",
        lambda: DummyOAuth(),
    )

    monkeypatch.setattr(
        "avanamy.api.routes.github_oauth.get_encryption_service",
        lambda: types.SimpleNamespace(encrypt=lambda v: f"enc-{v}"),
    )

    resp = client.post("/api/github/callback", json={"code": "code-1", "state": "state-1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["access_token_encrypted"] == "enc-token"
    assert data["user_info"]["login"] == "octo"


def test_callback_invalid_state_returns_error(client):
    github_routes._oauth_states.clear()
    resp = client.post("/api/github/callback", json={"code": "code-1", "state": "missing"})
    assert resp.status_code == 500


@pytest.mark.anyio
async def test_list_repositories(client, monkeypatch):
    monkeypatch.setattr(
        "avanamy.api.routes.github_oauth.get_encryption_service",
        lambda: types.SimpleNamespace(decrypt=lambda v: "token"),
    )

    class DummyGitHub:
        async def list_repositories(self):
            return [{"name": "repo"}]

    monkeypatch.setattr(
        "avanamy.services.github_api_service.GitHubAPIService",
        lambda _token: DummyGitHub(),
    )

    resp = client.get("/api/github/repositories", params={"access_token_encrypted": "enc"})
    assert resp.status_code == 200
    assert resp.json()["repositories"][0]["name"] == "repo"
