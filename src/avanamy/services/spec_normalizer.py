# src/avanamy/services/spec_normalizer.py

"""
OpenAPI Spec Normalizer for Diff Engine

Extracts ONLY the contract-relevant information from OpenAPI specs:
- Paths (endpoints)
- HTTP methods
- Required request fields
- Required response fields

Everything else (descriptions, examples, servers, security) is intentionally discarded.

Design Principles:
1. Deterministic - same input always produces same output
2. Minimal - only breaking-change-relevant fields
3. Lossy - discards noise on purpose
4. Version-agnostic - no timestamps or generated IDs
"""

from __future__ import annotations
from typing import List, Optional, Union
import logging
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options"}


def normalize_openapi_spec(raw_spec: dict) -> dict:
    """
    Convert an OpenAPI spec into a deterministic normalized structure suitable for diffing.
    
    Input: Full OpenAPI 3.x spec (dict from JSON/YAML parse)
    Output: Minimal normalized contract structure
    
    Example output:
    {
        "paths": {
            "/users": {
                "GET": {
                    "request": {"required_fields": []},
                    "response": {"required_fields": ["id", "email"]}
                },
                "POST": {
                    "request": {"required_fields": ["email", "name"]},
                    "response": {"required_fields": ["id"]}
                }
            }
        }
    }
    
    Args:
        raw_spec: Parsed OpenAPI spec (typically from parse_api_spec)
        
    Returns:
        Normalized spec dict with deterministic structure
    """
    with tracer.start_as_current_span("service.normalize_openapi_spec") as span:
        if not isinstance(raw_spec, dict):
            logger.warning("normalize_openapi_spec received non-dict input: %s", type(raw_spec))
            return {"paths": {}}
        
        paths = raw_spec.get("paths", {})
        
        if not paths:
            logger.warning("OpenAPI spec has no 'paths' - returning empty normalized spec")
            span.set_attribute("paths.count", 0)
            return {"paths": {}}
        
        normalized = {"paths": {}}

        # Sort paths for deterministic output
        for path in sorted(paths.keys()):
            path_item = paths[path]
            
            if not isinstance(path_item, dict):
                logger.warning("Path '%s' is not a dict, skipping", path)
                continue
            
            methods_out = {}

            # Sort methods for deterministic output
            for method in sorted(path_item.keys()):
                method_lower = method.lower()
                
                # Skip non-HTTP methods (like $ref, parameters, etc.)
                if method_lower not in HTTP_METHODS:
                    continue

                operation = path_item[method]
                
                if not isinstance(operation, dict):
                    logger.warning("Method '%s' on path '%s' is not a dict, skipping", method, path)
                    continue

                request_required = _extract_required_fields_from_request(operation)
                response_required = _extract_required_fields_from_response(operation)

                # Use uppercase method names for consistency
                methods_out[method.upper()] = {
                    "request": {
                        "required_fields": sorted(request_required),
                    },
                    "response": {
                        "required_fields": sorted(response_required),
                    },
                }

            # Only include paths that have at least one valid method
            if methods_out:
                normalized["paths"][path] = methods_out
        
        endpoint_count = len(normalized["paths"])
        span.set_attribute("endpoints.count", endpoint_count)
        logger.info("Normalized OpenAPI spec: %d endpoints", endpoint_count)

        return normalized


def _extract_required_fields_from_request(operation: dict) -> List[str]:
    """
    Extract required field names from request body schema.
    
    Looks at: requestBody → content → application/json → schema → required
    
    Args:
        operation: OpenAPI operation object (GET, POST, etc.)
        
    Returns:
        List of required field names (may be empty)
    """
    request_body = operation.get("requestBody", {})
    
    if not isinstance(request_body, dict):
        return []
    
    content = request_body.get("content", {})
    
    if not isinstance(content, dict):
        return []
    
    # Prefer application/json, fall back to first content type if needed
    json_body = content.get("application/json")
    
    if not json_body and content:
        # If no application/json, try the first available content type
        first_content_type = next(iter(content.keys()), None)
        if first_content_type:
            json_body = content[first_content_type]
            logger.debug("Using content type '%s' instead of application/json", first_content_type)
    
    if not isinstance(json_body, dict):
        return []
    
    schema = json_body.get("schema", {})
    
    if not isinstance(schema, dict):
        return []
    
    # Handle $ref in schema (common pattern)
    if "$ref" in schema:
        # For now, we can't resolve $refs without the full spec context
        # Future enhancement: resolve $refs from components/schemas
        logger.debug("Schema contains $ref, cannot extract required fields without resolution")
        return []
    
    required = schema.get("required", [])
    
    if not isinstance(required, list):
        logger.warning("Schema 'required' field is not a list: %s", type(required))
        return []
    
    return [str(field) for field in required if field]


def _extract_required_fields_from_response(operation: dict) -> List[str]:
    """
    Extract required field names from response body schema.
    
    Strategy:
    1. Prefer status code 200
    2. Fall back to 201
    3. Fall back to first 2xx status code
    4. Fall back to "default"
    
    Args:
        operation: OpenAPI operation object (GET, POST, etc.)
        
    Returns:
        List of required field names (may be empty)
    """
    responses = operation.get("responses", {})
    
    if not isinstance(responses, dict):
        return []

    # Determine success status code
    status = _determine_success_status(responses)
    
    if not status:
        logger.debug("No success status code found in responses")
        return []

    response = responses.get(status, {})
    
    if not isinstance(response, dict):
        return []
    
    content = response.get("content", {})
    
    if not isinstance(content, dict):
        return []
    
    # Prefer application/json, fall back to first content type
    json_body = content.get("application/json")
    
    if not json_body and content:
        first_content_type = next(iter(content.keys()), None)
        if first_content_type:
            json_body = content[first_content_type]
            logger.debug("Using content type '%s' instead of application/json", first_content_type)
    
    if not isinstance(json_body, dict):
        return []
    
    schema = json_body.get("schema", {})
    
    if not isinstance(schema, dict):
        return []
    
    # Handle $ref in schema
    if "$ref" in schema:
        logger.debug("Response schema contains $ref, cannot extract required fields without resolution")
        return []
    
    required = schema.get("required", [])
    
    if not isinstance(required, list):
        logger.warning("Response schema 'required' field is not a list: %s", type(required))
        return []
    
    return [str(field) for field in required if field]


def _determine_success_status(responses: dict) -> Optional[Union[str, int]]:
    """
    Determine which response status code to use for extracting schema.
    
    Handles both string status codes ("200") and integer status codes (200)
    which can occur depending on the parser (JSON vs YAML).
    
    Priority:
    1. 200 (most common success)
    2. 201 (created)
    3. First 2xx code found
    4. "default" if no 2xx found
    
    Args:
        responses: OpenAPI responses object
        
    Returns:
        Status code (as it appears in responses dict) or None
    """
    # Prefer 200 (check both string and int)
    if "200" in responses:
        return "200"
    if 200 in responses:
        return 200
    
    # Then 201
    if "201" in responses:
        return "201"
    if 201 in responses:
        return 201
    
    # Then any 2xx (handle both string and int)
    for code in sorted(responses.keys(), key=str):
        code_str = str(code)
        if code_str.startswith("2"):
            return code
    
    # Fall back to "default"
    if "default" in responses:
        return "default"
    
    return None