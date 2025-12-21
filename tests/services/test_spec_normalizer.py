# tests/services/test_openapi_normalizer.py

"""
Tests for OpenAPI Normalizer

These tests ensure:
1. Deterministic output (same input = same output)
2. Correct extraction of required fields
3. Proper handling of edge cases
4. Lossy behavior (discards noise)
"""
from avanamy.services.spec_normalizer import normalize_openapi_spec


def test_normalizes_required_fields():
    raw_spec = {
        "paths": {
            "/orders": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "required": ["order_id", "amount"]
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "required": ["status"]
                                    }
                                }
                            }
                        }
                    },
                }
            }
        }
    }

    normalized = normalize_openapi_spec(raw_spec)

    assert normalized == {
        "paths": {
            "/orders": {
                "POST": {
                    "request": {
                        "required_fields": ["amount", "order_id"]
                    },
                    "response": {
                        "required_fields": ["status"]
                    },
                }
            }
        }
    }

def test_handles_missing_request_body():
    raw_spec = {
        "paths": {
            "/health": {
                "get": {
                    "responses": {
                        "200": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "required": []
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    normalized = normalize_openapi_spec(raw_spec)

    assert normalized["paths"]["/health"]["GET"]["request"]["required_fields"] == []

class TestNormalizeOpenAPISpec:
    """Test the main normalization function"""
    
    def test_empty_spec(self):
        """Empty spec should return empty paths"""
        result = normalize_openapi_spec({})
        assert result == {"paths": {}}
    
    def test_spec_with_no_paths(self):
        """Spec without paths key should return empty paths"""
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test", "version": "1.0.0"}
        }
        result = normalize_openapi_spec(spec)
        assert result == {"paths": {}}
    
    def test_simple_get_endpoint(self):
        """Test basic GET endpoint normalization"""
        spec = {
            "paths": {
                "/users": {
                    "get": {
                        "summary": "Get users",  # Should be discarded
                        "description": "Returns all users",  # Should be discarded
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "required": ["id", "email"]
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        result = normalize_openapi_spec(spec)
        
        assert "/users" in result["paths"]
        assert "GET" in result["paths"]["/users"]
        assert result["paths"]["/users"]["GET"]["request"]["required_fields"] == []
        assert result["paths"]["/users"]["GET"]["response"]["required_fields"] == []
        # Note: Array responses don't have top-level required fields
    
    def test_post_endpoint_with_required_fields(self):
        """Test POST endpoint with required request and response fields"""
        spec = {
            "paths": {
                "/orders": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "required": ["order_id", "amount", "currency"],
                                        "properties": {
                                            "order_id": {"type": "string"},
                                            "amount": {"type": "number"},
                                            "currency": {"type": "string"},
                                            "notes": {"type": "string"}  # optional
                                        }
                                    }
                                }
                            }
                        },
                        "responses": {
                            "201": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "required": ["id", "status"],
                                            "properties": {
                                                "id": {"type": "string"},
                                                "status": {"type": "string"},
                                                "created_at": {"type": "string"}  # optional
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        result = normalize_openapi_spec(spec)
        
        assert result == {
            "paths": {
                "/orders": {
                    "POST": {
                        "request": {
                            "required_fields": ["amount", "currency", "order_id"]  # Sorted!
                        },
                        "response": {
                            "required_fields": ["id", "status"]  # Sorted!
                        }
                    }
                }
            }
        }
    
    def test_multiple_methods_same_path(self):
        """Test path with multiple HTTP methods"""
        spec = {
            "paths": {
                "/users/{id}": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "required": ["id", "name"]
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "delete": {
                        "responses": {
                            "204": {
                                "description": "Deleted"
                            }
                        }
                    }
                }
            }
        }
        
        result = normalize_openapi_spec(spec)
        
        assert "GET" in result["paths"]["/users/{id}"]
        assert "DELETE" in result["paths"]["/users/{id}"]
        # Methods should be sorted alphabetically
        methods = list(result["paths"]["/users/{id}"].keys())
        assert methods == sorted(methods)
    
    def test_deterministic_ordering(self):
        """Test that output is deterministically ordered"""
        spec = {
            "paths": {
                "/zebra": {"get": {"responses": {"200": {}}}},
                "/apple": {"get": {"responses": {"200": {}}}},
                "/middle": {"get": {"responses": {"200": {}}}},
            }
        }
        
        result = normalize_openapi_spec(spec)
        
        # Paths should be sorted
        paths = list(result["paths"].keys())
        assert paths == ["/apple", "/middle", "/zebra"]
    
    def test_ignores_non_http_methods(self):
        """Test that non-HTTP methods like $ref, parameters are ignored"""
        spec = {
            "paths": {
                "/users": {
                    "$ref": "#/components/paths/Users",  # Should be ignored
                    "parameters": [],  # Should be ignored
                    "get": {
                        "responses": {"200": {}}
                    }
                }
            }
        }
        
        result = normalize_openapi_spec(spec)
        
        # Only GET should be present
        assert list(result["paths"]["/users"].keys()) == ["GET"]
    
    def test_discards_descriptions_and_examples(self):
        """Test that noise (descriptions, examples, etc.) is discarded"""
        spec = {
            "paths": {
                "/users": {
                    "get": {
                        "summary": "This is noise",
                        "description": "This is also noise",
                        "tags": ["users"],
                        "deprecated": False,
                        "responses": {
                            "200": {
                                "description": "Success response description",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "description": "User schema description",
                                            "required": ["id"],
                                            "example": {"id": "123"}  # Noise
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        result = normalize_openapi_spec(spec)
        
        # Result should be minimal - only required fields
        assert result == {
            "paths": {
                "/users": {
                    "GET": {
                        "request": {"required_fields": []},
                        "response": {"required_fields": ["id"]}
                    }
                }
            }
        }
    
    def test_handles_missing_required_field(self):
        """Test that missing 'required' field defaults to empty list"""
        spec = {
            "paths": {
                "/users": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"}
                                        }
                                        # No 'required' field
                                    }
                                }
                            }
                        },
                        "responses": {"200": {}}
                    }
                }
            }
        }
        
        result = normalize_openapi_spec(spec)
        
        assert result["paths"]["/users"]["POST"]["request"]["required_fields"] == []

class TestDeterminism:
    """Test that normalization is deterministic"""
    
    def test_same_input_same_output(self):
        """Running normalization twice should produce identical results"""
        spec = {
            "paths": {
                "/users": {
                    "get": {
                        "responses": {
                            "200": {
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "required": ["id", "name"]
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
        
        result1 = normalize_openapi_spec(spec)
        result2 = normalize_openapi_spec(spec)
        
        assert result1 == result2
    
    def test_field_ordering_deterministic(self):
        """Required fields should always be sorted"""
        spec = {
            "paths": {
                "/users": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "required": ["zebra", "apple", "middle"]
                                    }
                                }
                            }
                        },
                        "responses": {"200": {}}
                    }
                }
            }
        }
        
        result = normalize_openapi_spec(spec)
        
        # Fields should be sorted alphabetically
        fields = result["paths"]["/users"]["POST"]["request"]["required_fields"]
        assert fields == ["apple", "middle", "zebra"]