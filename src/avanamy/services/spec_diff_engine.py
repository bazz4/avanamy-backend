# src/avanamy/services/spec_diff_engine.py

"""
Diff Engine for Normalized OpenAPI Specs

Compares two normalized specs and identifies:
- Breaking changes (endpoint/method/required field removals)
- Non-breaking changes (additions)

Output is stored in VersionHistory.diff column and used for:
- Change detection
- Breaking change alerts
- Migration guides
- AI summaries (future)
"""

from __future__ import annotations
from typing import List, Dict, Any
import logging
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def diff_normalized_specs(old_spec: dict, new_spec: dict) -> dict:
    """
    Compare two normalized specs and identify changes.
    
    Args:
        old_spec: Previous normalized spec
        new_spec: New normalized spec
        
    Returns:
        Diff object with breaking and non-breaking changes
        
    Example:
        {
            "breaking": true,
            "changes": [
                {
                    "type": "endpoint_removed",
                    "path": "/users",
                    "method": "GET"
                },
                {
                    "type": "required_request_field_added",
                    "path": "/orders",
                    "method": "POST",
                    "field": "customer_id"
                }
            ]
        }
    """
    with tracer.start_as_current_span("service.diff_normalized_specs") as span:
        changes = []
        
        old_paths = old_spec.get("paths", {})
        new_paths = new_spec.get("paths", {})
        
        # Find removed endpoints (BREAKING)
        for path in old_paths:
            if path not in new_paths:
                changes.append({
                    "type": "endpoint_removed",
                    "path": path,
                })
                logger.info("Detected removed endpoint: %s", path)
        
        # Find added endpoints (non-breaking)
        for path in new_paths:
            if path not in old_paths:
                changes.append({
                    "type": "endpoint_added",
                    "path": path,
                })
                logger.info("Detected added endpoint: %s", path)
        
        # Compare endpoints that exist in both
        for path in old_paths:
            if path not in new_paths:
                continue  # Already handled as removed
            
            old_methods = old_paths[path]
            new_methods = new_paths[path]
            
            # Find removed methods (BREAKING)
            for method in old_methods:
                if method not in new_methods:
                    changes.append({
                        "type": "method_removed",
                        "path": path,
                        "method": method,
                    })
                    logger.info("Detected removed method: %s %s", method, path)
            
            # Find added methods (non-breaking)
            for method in new_methods:
                if method not in old_methods:
                    changes.append({
                        "type": "method_added",
                        "path": path,
                        "method": method,
                    })
                    logger.info("Detected added method: %s %s", method, path)
            
            # Compare methods that exist in both
            for method in old_methods:
                if method not in new_methods:
                    continue  # Already handled as removed
                
                old_operation = old_methods[method]
                new_operation = new_methods[method]
                
                # Compare request required fields
                request_changes = _diff_required_fields(
                    old_operation.get("request", {}).get("required_fields", []),
                    new_operation.get("request", {}).get("required_fields", []),
                    path=path,
                    method=method,
                    field_type="request",
                )
                changes.extend(request_changes)
                
                # Compare response required fields
                response_changes = _diff_required_fields(
                    old_operation.get("response", {}).get("required_fields", []),
                    new_operation.get("response", {}).get("required_fields", []),
                    path=path,
                    method=method,
                    field_type="response",
                )
                changes.extend(response_changes)
        
        # Determine if any changes are breaking
        breaking = any(
            change["type"] in {
                "endpoint_removed",
                "method_removed",
                "required_request_field_added",
                "required_response_field_removed",
            }
            for change in changes
        )
        
        span.set_attribute("diff.changes_count", len(changes))
        span.set_attribute("diff.breaking", breaking)
        
        logger.info(
            "Diff complete: %d changes, breaking=%s",
            len(changes),
            breaking,
        )
        
        return {
            "breaking": breaking,
            "changes": changes,
        }


def _diff_required_fields(
    old_fields: List[str],
    new_fields: List[str],
    *,
    path: str,
    method: str,
    field_type: str,
) -> List[Dict[str, Any]]:
    """
    Compare required fields and identify changes.
    
    Args:
        old_fields: Required fields in old spec
        new_fields: Required fields in new spec
        path: API path
        method: HTTP method
        field_type: "request" or "response"
        
    Returns:
        List of change objects
    """
    changes = []
    
    old_set = set(old_fields)
    new_set = set(new_fields)
    
    # Fields removed
    removed = old_set - new_set
    for field in sorted(removed):
        if field_type == "request":
            # Removing required request field is non-breaking (less strict)
            change_type = "required_request_field_removed"
        else:
            # Removing required response field is BREAKING (client expects it)
            change_type = "required_response_field_removed"
        
        changes.append({
            "type": change_type,
            "path": path,
            "method": method,
            "field": field,
        })
        logger.info(
            "Detected %s: %s %s field=%s",
            change_type,
            method,
            path,
            field,
        )
    
    # Fields added
    added = new_set - old_set
    for field in sorted(added):
        if field_type == "request":
            # Adding required request field is BREAKING (client must provide it)
            change_type = "required_request_field_added"
        else:
            # Adding required response field is non-breaking (client gets more data)
            change_type = "required_response_field_added"
        
        changes.append({
            "type": change_type,
            "path": path,
            "method": method,
            "field": field,
        })
        logger.info(
            "Detected %s: %s %s field=%s",
            change_type,
            method,
            path,
            field,
        )
    
    return changes