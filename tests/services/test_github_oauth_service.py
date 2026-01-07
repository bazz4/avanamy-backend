import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock

from avanamy.services.github_oauth_service import GitHubOAuthService


def _set_oauth_env(monkeypatch):
    monkeypatch.setenv("GITHUB_CLIENT_ID", "client-id")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "client-secret")


def test_init_requires_credentials(monkeypatch):
    monkeypatch.delenv("GITHUB_CLIENT_ID", raising=False)
    monkeypatch.delenv("GITHUB_CLIENT_SECRET", raising=False)

    with pytest.raises(ValueError):
        GitHubOAuthService()


def test_get_authorization_url(monkeypatch):
    _set_oauth_env(monkeypatch)
    service = GitHubOAuthService()

    url = service.get_authorization_url("state-123")

    assert "client_id=client-id" in url
    assert "scope=repo" in url
    assert "state=state-123" in url


@pytest.mark.anyio
async def test_exchange_code_for_token_success(monkeypatch):
    _set_oauth_env(monkeypatch)
    service = GitHubOAuthService()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"access_token": "token-123"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    mock_client_class = MagicMock()
    mock_client_class.return_value.__aenter__.return_value = mock_client

    monkeypatch.setattr(
        "avanamy.services.github_oauth_service.httpx.AsyncClient",
        mock_client_class,
    )

    token = await service.exchange_code_for_token("code-abc")

    assert token == "token-123"


@pytest.mark.anyio
async def test_exchange_code_for_token_missing_token(monkeypatch):
    _set_oauth_env(monkeypatch)
    service = GitHubOAuthService()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"error_description": "bad"}

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    mock_client_class = MagicMock()
    mock_client_class.return_value.__aenter__.return_value = mock_client

    monkeypatch.setattr(
        "avanamy.services.github_oauth_service.httpx.AsyncClient",
        mock_client_class,
    )

    with pytest.raises(ValueError):
        await service.exchange_code_for_token("code-abc")


@pytest.mark.anyio
async def test_exchange_code_for_token_http_error(monkeypatch):
    _set_oauth_env(monkeypatch)
    service = GitHubOAuthService()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock(side_effect=httpx.HTTPError("boom"))

    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_response)

    mock_client_class = MagicMock()
    mock_client_class.return_value.__aenter__.return_value = mock_client

    monkeypatch.setattr(
        "avanamy.services.github_oauth_service.httpx.AsyncClient",
        mock_client_class,
    )

    with pytest.raises(ValueError):
        await service.exchange_code_for_token("code-abc")


@pytest.mark.anyio
async def test_get_user_info_success(monkeypatch):
    _set_oauth_env(monkeypatch)
    service = GitHubOAuthService()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {
        "login": "octo",
        "id": 123,
        "name": "Octo Cat",
        "email": "octo@example.com",
    }

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    mock_client_class = MagicMock()
    mock_client_class.return_value.__aenter__.return_value = mock_client

    monkeypatch.setattr(
        "avanamy.services.github_oauth_service.httpx.AsyncClient",
        mock_client_class,
    )

    info = await service.get_user_info("token-abc")

    assert info["login"] == "octo"
    assert info["id"] == 123


@pytest.mark.anyio
async def test_get_user_info_http_error(monkeypatch):
    _set_oauth_env(monkeypatch)
    service = GitHubOAuthService()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock(side_effect=httpx.HTTPError("boom"))

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    mock_client_class = MagicMock()
    mock_client_class.return_value.__aenter__.return_value = mock_client

    monkeypatch.setattr(
        "avanamy.services.github_oauth_service.httpx.AsyncClient",
        mock_client_class,
    )

    with pytest.raises(ValueError):
        await service.get_user_info("token-abc")
