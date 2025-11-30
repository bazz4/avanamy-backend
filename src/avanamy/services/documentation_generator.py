# src/avanamy/services/documentation_generator.py

from __future__ import annotations
from typing import Any, Dict, List


def generate_markdown_from_normalized_spec(spec: Dict[str, Any]) -> str:
    """
    Generate Stripe-style API documentation in Markdown from a normalized spec.

    This function assumes:
      - Keys have been lowercased by normalize_api_spec
      - For OpenAPI specs:
          - top-level 'info', 'paths', 'components', 'webhooks' etc. may exist

    If we can't detect a typical OpenAPI shape, we fall back to a generic dump.
    """
    lines: List[str] = []

    if "paths" not in spec:
        return _generate_generic_markdown(spec)

    _add_overview_section(lines, spec)
    _add_authentication_section(lines, spec)
    _add_errors_section(lines, spec)
    _add_models_section(lines, spec)
    _add_endpoints_section(lines, spec)
    _add_webhooks_section(lines, spec)

    return "\n".join(lines).strip() + "\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _add_overview_section(lines: List[str], spec: Dict[str, Any]) -> None:
    info = spec.get("info", {}) or {}
    title = info.get("title") or "API Documentation"
    version = info.get("version")
    description = info.get("description")

    lines.append(f"# {title}")
    if version:
        lines.append(f"_Version: {version}_")
    lines.append("")

    if description:
        lines.append(description)
        lines.append("")

    servers = spec.get("servers", []) or []
    if servers:
        lines.append("## Base URLs")
        lines.append("")
        lines.append("| Environment | URL |")
        lines.append("|------------|-----|")
        for s in servers:
            url = s.get("url") or ""
            desc = s.get("description") or "Default"
            lines.append(f"| {desc} | `{url}` |")
        lines.append("")


def _add_authentication_section(lines: List[str], spec: Dict[str, Any]) -> None:
    components = spec.get("components", {}) or {}
    security_schemes = components.get("securityschemes", {}) or {}
    if not security_schemes:
        return

    lines.append("## Authentication")
    lines.append("")
    lines.append(
        "This API uses the following authentication methods. "
        "Include the appropriate credentials with each request."
    )
    lines.append("")

    for name, scheme in security_schemes.items():
        stype = scheme.get("type") or "unknown"
        desc = scheme.get("description") or ""
        lines.append(f"### {name}")
        lines.append("")
        lines.append(f"Type: `{stype}`")
        if scheme.get("scheme"):
            lines.append(f"Scheme: `{scheme.get('scheme')}`")
        if scheme.get("bearerformat"):
            lines.append(f"Bearer format: `{scheme.get('bearerformat')}`")
        if scheme.get("in"):
            lines.append(f"In: `{scheme.get('in')}`")
        if scheme.get("name"):
            lines.append(f"Header/parameter: `{scheme.get('name')}`")
        if desc:
            lines.append("")
            lines.append(desc)
        lines.append("")


def _add_errors_section(lines: List[str], spec: Dict[str, Any]) -> None:
    # For now we derive errors from responses across all paths.
    paths = spec.get("paths", {}) or {}

    collected: Dict[str, str] = {}
    for path, operations in paths.items():
        if not isinstance(operations, dict):
            continue
        for method, op in operations.items():
            if not isinstance(op, dict):
                continue
            responses = op.get("responses", {}) or {}
            for status_code, detail in responses.items():
                if not isinstance(detail, dict):
                    continue
                desc = detail.get("description") or ""
                existing = collected.get(status_code)
                # Prefer the longest description we see
                if desc and (existing is None or len(desc) > len(existing)):
                    collected[status_code] = desc

    if not collected:
        return

    lines.append("## Error Responses")
    lines.append("")
    lines.append("| Status Code | Description |")
    lines.append("|-------------|-------------|")
    for status, desc in sorted(collected.items(), key=lambda x: x[0]):
        safe_desc = desc.replace("\n", " ").strip()
        lines.append(f"| `{status}` | {safe_desc} |")
    lines.append("")


def _add_models_section(lines: List[str], spec: Dict[str, Any]) -> None:
    components = spec.get("components", {}) or {}
    schemas = components.get("schemas", {}) or {}
    if not schemas:
        return

    lines.append("## Models")
    lines.append("")
    lines.append(
        "These are the primary data models used in request and response payloads."
    )
    lines.append("")

    for model_name, model in schemas.items():
        lines.append(f"### {model_name}")
        lines.append("")

        desc = model.get("description")
        if desc:
            lines.append(desc)
            lines.append("")

        props = model.get("properties", {}) or {}
        required = set(model.get("required") or [])

        if props:
            lines.append("| Field | Type | Required | Description |")
            lines.append("|-------|------|----------|-------------|")
            for field_name, field in props.items():
                ftype = field.get("type") or field.get("format") or "object"
                is_req = "yes" if field_name in required else "no"
                fdesc = (field.get("description") or "").replace("\n", " ").strip()
                lines.append(
                    f"| `{field_name}` | `{ftype}` | {is_req} | {fdesc} |"
                )
            lines.append("")
        else:
            lines.append("_No explicit properties defined._")
            lines.append("")


def _add_endpoints_section(lines: List[str], spec: Dict[str, Any]) -> None:
    paths = spec.get("paths", {}) or {}
    if not paths:
        return

    # Quick index table
    lines.append("## Endpoints")
    lines.append("")
    lines.append("| Method | Path | Summary |")
    lines.append("|--------|------|---------|")

    flat_endpoints: List[Dict[str, Any]] = []

    for path, operations in paths.items():
        if not isinstance(operations, dict):
            continue

        for method, op in operations.items():
            if not isinstance(op, dict):
                continue

            http_method = method.upper()
            summary = op.get("summary") or op.get("operationid") or ""
            flat_endpoints.append(
                {
                    "method": http_method,
                    "path": path,
                    "summary": summary,
                    "op": op,
                }
            )

    for ep in flat_endpoints:
        summary = ep["summary"].replace("\n", " ").strip()
        lines.append(
            f"| `{ep['method']}` | `{ep['path']}` | {summary or ''} |"
        )
    lines.append("")

    # Detailed sections per endpoint
    for ep in flat_endpoints:
        _add_single_endpoint_section(lines, ep["path"], ep["method"], ep["op"])


def _add_single_endpoint_section(
    lines: List[str], path: str, method: str, op: Dict[str, Any]
) -> None:
    lines.append(f"### {method} {path}")
    lines.append("")

    summary = op.get("summary")
    description = op.get("description")

    if summary:
        lines.append(f"**Summary:** {summary}")
        lines.append("")
    if description:
        lines.append(description)
        lines.append("")

    # Parameters
    params = op.get("parameters", []) or []
    if params:
        lines.append("#### Parameters")
        lines.append("")
        lines.append("| Name | In | Type | Required | Description |")
        lines.append("|------|----|------|----------|-------------|")
        for p in params:
            name = p.get("name") or ""
            loc = p.get("in") or ""
            required = "yes" if p.get("required") else "no"
            schema = p.get("schema") or {}
            ptype = schema.get("type") or schema.get("format") or "string"
            desc = (p.get("description") or "").replace("\n", " ").strip()
            lines.append(
                f"| `{name}` | `{loc}` | `{ptype}` | {required} | {desc} |"
            )
        lines.append("")

    # Request body
    request_body = op.get("requestbody") or {}
    content = request_body.get("content") or {}
    if content:
        lines.append("#### Request Body")
        lines.append("")
        for mime, media in content.items():
            lines.append(f"- Content type: `{mime}`")
            schema = media.get("schema") or {}
            example = media.get("example") or media.get("examples")
            if schema:
                lines.append("")
                lines.append("Schema:")
                lines.append("")
                lines.append("```json")
                lines.append(_safe_json_example(schema))
                lines.append("```")
            if example:
                lines.append("")
                lines.append("Example:")
                lines.append("")
                lines.append("```json")
                lines.append(_safe_json_example(example))
                lines.append("```")
        lines.append("")

    # Responses
    responses = op.get("responses") or {}
    if responses:
        lines.append("#### Responses")
        lines.append("")
        for status_code, resp in responses.items():
            if not isinstance(resp, dict):
                continue
            desc = resp.get("description") or ""
            lines.append(f"- **{status_code}** – {desc}")
            content = resp.get("content") or {}
            # Prefer application/json
            media = content.get("application/json") or next(
                iter(content.values()), None
            )
            if media:
                example = media.get("example") or media.get("examples")
                schema = media.get("schema")
                if example:
                    lines.append("")
                    lines.append("  Example:")
                    lines.append("")
                    lines.append("  ```json")
                    for line in _safe_json_example(example).splitlines():
                        lines.append(f"  {line}")
                    lines.append("  ```")
                elif schema:
                    lines.append("")
                    lines.append("  Schema:")
                    lines.append("")
                    lines.append("  ```json")
                    for line in _safe_json_example(schema).splitlines():
                        lines.append(f"  {line}")
                    lines.append("  ```")
            lines.append("")


def _add_webhooks_section(lines: List[str], spec: Dict[str, Any]) -> None:
    # OpenAPI 3.1+ can have `webhooks` top-level; vendors sometimes use `x-webhooks`.
    webhooks = spec.get("webhooks") or spec.get("x-webhooks")
    if not webhooks or not isinstance(webhooks, dict):
        return

    lines.append("## Webhooks")
    lines.append("")
    for event_name, operations in webhooks.items():
        lines.append(f"### {event_name}")
        lines.append("")
        if not isinstance(operations, dict):
            continue
        for method, op in operations.items():
            if not isinstance(op, dict):
                continue
            http_method = method.upper()
            summary = op.get("summary") or ""
            desc = op.get("description") or ""
            lines.append(f"**{http_method}**")
            if summary:
                lines.append("")
                lines.append(f"_Summary_: {summary}")
            if desc:
                lines.append("")
                lines.append(desc)
            lines.append("")


def _safe_json_example(obj: Any) -> str:
    """
    Best-effort pretty "JSON-like" serialization for docs.
    We avoid importing json here to keep it simple if the structure
    has already been normalized to strings.
    """
    try:
        import json
        return json.dumps(obj, indent=2, ensure_ascii=False)
    except Exception:
        return str(obj)


def _generate_generic_markdown(spec: Dict[str, Any]) -> str:
    """
    Fallback for non-OpenAPI-like specs: just dump the normalized dict.
    """
    lines: List[str] = []
    lines.append("# API Documentation")
    lines.append("")
    lines.append(
        "_Note: The uploaded spec does not look like a standard OpenAPI document. "
        "Showing a generic view of the normalized structure._"
    )
    lines.append("")
    lines.append("```json")
    lines.append(_safe_json_example(spec))
    lines.append("```")
    lines.append("")
    return "\n".join(lines)
