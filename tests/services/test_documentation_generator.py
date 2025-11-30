import json
from avanamy.services.documentation_generator import generate_markdown_from_normalized_spec


# -------------------------------------------------------------
# Helper: A rich OpenAPI-like test spec with:
# - Tags
# - Models
# - Authentication
# - Example responses
# - Request body
# -------------------------------------------------------------
def _sample_spec():
    return {
        "openapi": "3.0.0",
        "info": {
            "title": "Demo API",
            "version": "1.0",
            "description": "A demo API for testing polished docs."
        },
        "servers": [
            {"url": "https://api.example.com", "description": "Production"}
        ],
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {
                    "type": "apiKey",
                    "name": "X-API-Key",
                    "in": "header",
                    "description": "Use your API key."
                }
            },
            "schemas": {
                "User": {
                    "description": "A user record.",
                    "required": ["id", "name"],
                    "properties": {
                        "id": {"type": "integer", "description": "User ID"},
                        "name": {"type": "string", "description": "Full name"},
                    }
                }
            }
        },
        "paths": {
            "/users": {
                "get": {
                    "summary": "List users",
                    "tags": ["Users"],
                    "description": "Returns all users.",
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "example": [
                                        {"id": 1, "name": "A"},
                                        {"id": 2, "name": "B"}
                                    ]
                                }
                            }
                        }
                    }
                }
            },
            "/users/{id}": {
                "post": {
                    "summary": "Create a user",
                    "tags": ["Users"],
                    "description": "Creates a new user.",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {"type": "object", "properties": {
                                    "name": {"type": "string"}
                                }},
                                "example": {"name": "Test"}
                            }
                        }
                    },
                    "responses": {
                        "201": {
                            "description": "Created",
                            "content": {
                                "application/json": {
                                    "example": {"id": 10, "name": "Test"}
                                }
                            }
                        }
                    }
                }
            }
        }
    }


# -------------------------------------------------------------
# Tests for Major Sections
# -------------------------------------------------------------

def test_toc_is_present():
    md = generate_markdown_from_normalized_spec(_sample_spec())
    assert "## Table of Contents" in md
    assert "- [Models](#models)" in md
    assert "- [Users](#users)" in md


def test_authentication_section_present():
    md = generate_markdown_from_normalized_spec(_sample_spec())
    assert "## Authentication" in md
    assert "ApiKeyAuth" in md
    assert "X-API-Key" in md
    assert "header" in md


def test_models_section_present_and_preserves_casing():
    md = generate_markdown_from_normalized_spec(_sample_spec())
    assert "## Models" in md
    assert "### User" in md  # casing preserved
    assert "`id`" in md
    assert "`name`" in md


def test_endpoints_grouped_by_tags():
    md = generate_markdown_from_normalized_spec(_sample_spec())
    # Group header
    assert "## Users" in md

    # Endpoint summary rows
    assert "| `GET` | `/users` | List users |" in md
    assert "| `POST` | `/users/{id}` | Create a user |" in md


def test_endpoint_detail_sections_created():
    md = generate_markdown_from_normalized_spec(_sample_spec())

    # Anchored detail section for GET /users
    assert "### GET /users" in md
    assert "**Summary:** List users" in md
    assert "Returns all users." in md

    # POST route
    assert "### POST /users/{id}" in md
    assert "Creates a new user." in md


def test_try_it_and_examples_present():
    md = generate_markdown_from_normalized_spec(_sample_spec())

    # Try-it block exists
    assert "#### Try It" in md
    assert "curl -X GET /users" in md or "curl -X POST /users/{id}" in md

    # Multi-language examples
    assert "Python" in md
    assert "Node.js" in md
    assert "C#" in md


def test_request_body_and_response_sections():
    md = generate_markdown_from_normalized_spec(_sample_spec())

    # Request body section for POST
    assert "#### Request Body" in md
    assert '"name"' in md  # schema presence

    # Responses
    assert "#### Responses" in md
    assert "**200** – OK" in md or "**201** – Created" in md

    # Example response (pretty printed)
    assert '"id"' in md
    assert '"name"' in md


def test_webhooks_section_optional():
    """
    Webhooks aren't in this sample spec, so ensure the section does NOT appear.
    """
    md = generate_markdown_from_normalized_spec(_sample_spec())
    assert "## Webhooks" not in md
