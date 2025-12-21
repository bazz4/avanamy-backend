# tests/services/test_ai_summary_service.py

"""Tests for AI summary generation service."""

import pytest
from unittest.mock import Mock, patch
from avanamy.services.ai_summary_service import (
    generate_diff_summary,
    _build_summary_prompt,
)


class TestGenerateDiffSummary:
    """Tests for generate_diff_summary function."""

    def test_returns_none_when_no_changes(self):
        """Should return None when diff has no changes."""
        diff = {"breaking": False, "changes": []}
        result = generate_diff_summary(diff, version_from=1, version_to=2)
        assert result is None

    def test_returns_none_when_no_api_key(self, monkeypatch):
        """Should return None when ANTHROPIC_API_KEY is not set."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        
        diff = {
            "breaking": True,
            "changes": [
                {"type": "endpoint_removed", "path": "/users", "method": "GET"}
            ]
        }
        
        result = generate_diff_summary(diff, version_from=1, version_to=2)
        assert result is None

    @patch("avanamy.services.ai_summary_service.anthropic.Anthropic")
    def test_generates_summary_with_valid_api_key(self, mock_anthropic_class, monkeypatch):
        """Should generate summary when API key is valid."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        
        # Mock the API response
        mock_client = Mock()
        mock_message = Mock()
        mock_content = Mock()
        mock_content.text = "This is a breaking change summary."
        mock_message.content = [mock_content]
        mock_client.messages.create.return_value = mock_message
        mock_anthropic_class.return_value = mock_client
        
        diff = {
            "breaking": True,
            "changes": [
                {"type": "required_response_field_removed", "path": "/users", "method": "GET", "field": "name"}
            ]
        }
        
        result = generate_diff_summary(diff, version_from=1, version_to=2)
        
        assert result == "This is a breaking change summary."
        mock_client.messages.create.assert_called_once()
        
        # Verify correct model is used
        call_args = mock_client.messages.create.call_args
        assert call_args.kwargs["model"] == "claude-sonnet-4-20250514"

    @patch("avanamy.services.ai_summary_service.anthropic.Anthropic")
    def test_handles_api_error_gracefully(self, mock_anthropic_class, monkeypatch):
        """Should return None and not raise when API call fails."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        
        mock_client = Mock()
        mock_client.messages.create.side_effect = Exception("API Error")
        mock_anthropic_class.return_value = mock_client
        
        diff = {
            "breaking": True,
            "changes": [{"type": "endpoint_removed", "path": "/users"}]
        }
        
        result = generate_diff_summary(diff, version_from=1, version_to=2)
        assert result is None

    @patch("avanamy.services.ai_summary_service.anthropic.Anthropic")
    def test_handles_empty_response(self, mock_anthropic_class, monkeypatch):
        """Should return None when API returns empty content."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key")
        
        mock_client = Mock()
        mock_message = Mock()
        mock_message.content = []
        mock_client.messages.create.return_value = mock_message
        mock_anthropic_class.return_value = mock_client
        
        diff = {
            "breaking": True,
            "changes": [{"type": "endpoint_removed", "path": "/users"}]
        }
        
        result = generate_diff_summary(diff, version_from=1, version_to=2)
        assert result is None


class TestBuildSummaryPrompt:
    """Tests for _build_summary_prompt helper function."""

    def test_builds_prompt_for_breaking_changes(self):
        """Should build correct prompt for breaking changes."""
        diff = {
            "breaking": True,
            "changes": [
                {"type": "required_response_field_removed", "path": "/users", "method": "GET", "field": "name"},
                {"type": "required_request_field_added", "path": "/users", "method": "POST", "field": "phone"},
            ]
        }
        
        prompt = _build_summary_prompt(diff, version_from=1, version_to=2)
        
        assert "version 1 and version 2" in prompt
        assert "required_response_field_removed: GET /users → name" in prompt
        assert "required_request_field_added: POST /users → phone" in prompt
        assert "Breaking changes detected: Yes" in prompt

    def test_builds_prompt_for_non_breaking_changes(self):
        """Should build correct prompt for non-breaking changes."""
        diff = {
            "breaking": False,
            "changes": [
                {"type": "endpoint_added", "path": "/products", "method": "GET"},
            ]
        }
        
        prompt = _build_summary_prompt(diff, version_from=2, version_to=3)
        
        assert "version 2 and version 3" in prompt
        assert "endpoint_added: GET /products" in prompt
        assert "Breaking changes detected: No" in prompt

    def test_handles_changes_without_method(self):
        """Should handle changes that don't have method field."""
        diff = {
            "breaking": False,
            "changes": [
                {"type": "endpoint_added", "path": "/products"},
            ]
        }
        
        prompt = _build_summary_prompt(diff, version_from=1, version_to=2)
        
        assert "endpoint_added: /products" in prompt

    def test_handles_changes_without_field(self):
        """Should handle changes that don't have field attribute."""
        diff = {
            "breaking": True,
            "changes": [
                {"type": "method_removed", "path": "/users", "method": "DELETE"},
            ]
        }
        
        prompt = _build_summary_prompt(diff, version_from=1, version_to=2)
        
        assert "method_removed: DELETE /users" in prompt