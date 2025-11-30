import json
from avanamy.services.documentation_generator import (
    generate_markdown_from_normalized_spec,
)


def test_generate_markdown_minimal_openapi():
    schema = {
        "info": {"title": "Test API", "version": "1.0", "description": "A sample API"},
        "paths": {
            "/users": {
                "get": {
                    "summary": "Get users",
                    "description": "Returns a list of users",
                    "responses": {
                        "200": {"description": "OK"},
                        "404": {"description": "Not found"},
                    },
                }
            }
        },
        "components": {"schemas": {}},
    }

    md = generate_markdown_from_normalized_spec(schema)

    # Header and version
    assert "# Test API" in md
    assert "_Version: 1.0_" in md

    # Endpoint index
    assert "| `GET` | `/users` | Get users |" in md

    # Detailed endpoint section
    assert "### GET /users" in md
    assert "Returns a list of users" in md

    # Error table
    assert "| `404` | Not found |" in md


def test_generate_markdown_generic_for_non_openapi():
    schema = {"foo": "bar", "items": [1, 2, 3]}

    md = generate_markdown_from_normalized_spec(schema)
    assert "# API Documentation" in md
    assert "generic view of the normalized structure" in md
    assert "foo" in md
    assert "items" in md
