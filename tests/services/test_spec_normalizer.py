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
