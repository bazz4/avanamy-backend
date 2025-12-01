# src/avanamy/services/documentation_generator.py

from __future__ import annotations
from typing import Any, Dict, List
import json
import logging

from opentelemetry import trace
from prometheus_client import Counter, REGISTRY


logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


# ------------------------------------------------------------
# Prometheus counter (safe to reuse if already registered)
# ------------------------------------------------------------

def _safe_counter(name: str, documentation: str):
    try:
        return Counter(name, documentation)
    except ValueError:
        return REGISTRY._names_to_collectors[name]


markdown_generation_counter = _safe_counter(
    "avanamy_markdown_gen_total",
    "Number of API docs markdown generations"
)


# ============================================================
#  MAIN ENTRY POINT
# ============================================================

def generate_markdown_from_normalized_spec(spec: Dict[str, Any]) -> str:
    """
    Generate polished Markdown documentation based on a normalized
    OpenAPI-like schema.
    """

    markdown_generation_counter.inc()

    with tracer.start_as_current_span("service.generate_markdown") as span:
        span.set_attribute("has.paths", bool(spec.get("paths")))
        span.set_attribute("has.components", bool(spec.get("components")))

        logger.info("Starting Markdown generation")

        try:
            if "paths" not in spec:
                logger.warning("Spec has no paths; using fallback generator")
                return _generate_generic_markdown(spec)

            lines: List[str] = []

            _add_overview(lines, spec)
            _add_table_of_contents(lines, spec)
            _add_auth_section(lines, spec)
            _add_models_section(lines, spec)
            _add_endpoint_groups(lines, spec)
            _add_webhooks_section(lines, spec)

            result = "\n".join(lines).strip() + "\n"

            span.set_attribute("markdown.length", len(result))
            logger.debug("Markdown generation complete; length=%d", len(result))

            return result

        except Exception:
            logger.exception("Failed to generate markdown")
            raise


# ============================================================
#  TABLE OF CONTENTS
# ============================================================

def _add_table_of_contents(lines: List[str], spec: Dict[str, Any]):
    lines.append("## Table of Contents\n")

    lines.append("- [Overview](#overview)")
    lines.append("- [Authentication](#authentication)")

    if "components" in spec and spec["components"].get("schemas"):
        lines.append("- [Models](#models)")

    tag_map = _group_paths_by_tag(spec)
    for tag in tag_map:
        anchor = tag.lower().replace(" ", "-")
        lines.append(f"- [{tag}](#{anchor})")

        for ep in tag_map[tag]:
            method = ep["method"]
            path = ep["path"]
            anchor = f"{method.lower()}-{path.strip('/').replace('/', '-')}"
            lines.append(f"  - `{method} {path}` → [{path}](#{anchor})")

    if spec.get("webhooks") or spec.get("x-webhooks"):
        lines.append("- [Webhooks](#webhooks)")

    lines.append("\n---\n")


# ============================================================
#  OVERVIEW
# ============================================================

def _add_overview(lines: List[str], spec: Dict[str, Any]):
    info = spec.get("info", {})
    title = info.get("title", "API Documentation")
    version = info.get("version")
    description = info.get("description")

    lines.append(f"# {title}")
    if version:
        lines.append(f"_Version: {version}_\n")
    if description:
        lines.append(f"{description}\n")

    servers = spec.get("servers", [])
    if servers:
        lines.append("## Base URLs\n")
        lines.append("| Environment | URL |")
        lines.append("|------------|-----|")
        for s in servers:
            desc = s.get("description", "Default")
            url = s.get("url", "")
            lines.append(f"| {desc} | `{url}` |")
        lines.append("")


# ============================================================
#  AUTHENTICATION
# ============================================================

def _add_auth_section(lines: List[str], spec: Dict[str, Any]):
    components = spec.get("components", {})
    schemes = components.get("securitySchemes") or components.get("securityschemes")

    lines.append("## Authentication\n")

    if not schemes:
        lines.append("_This API does not define security requirements._\n")
        return

    for name, scheme in schemes.items():
        lines.append(f"### {name}\n")
        stype = scheme.get("type", "unknown")
        lines.append(f"- **Type:** `{stype}`")
        if scheme.get("scheme"):
            lines.append(f"- **Scheme:** `{scheme['scheme']}`")
        if scheme.get("bearerFormat"):
            lines.append(f"- **Bearer Format:** `{scheme['bearerFormat']}`")
        if scheme.get("in"):
            lines.append(f"- **In:** `{scheme['in']}`")
        if scheme.get("name"):
            lines.append(f"- **Parameter:** `{scheme['name']}`")
        if scheme.get("description"):
            lines.append(f"\n{scheme['description']}")
        lines.append("")


# ============================================================
#  MODELS
# ============================================================

def _add_models_section(lines: List[str], spec: Dict[str, Any]):
    components = spec.get("components", {})
    schemas = components.get("schemas", {})

    if not schemas:
        return

    lines.append("## Models\n")

    for model_name, model in schemas.items():
        lines.append(f"### {model_name}\n")

        desc = model.get("description")
        if desc:
            lines.append(desc + "\n")

        props = model.get("properties", {})
        required = set(model.get("required", []))

        if props:
            lines.append("| Field | Type | Required | Description |")
            lines.append("|-------|------|----------|-------------|")
            for field_name, field in props.items():
                ftype = field.get("type", field.get("format", "object"))
                is_req = "yes" if field_name in required else "no"
                fdesc = field.get("description", "").replace("\n", " ")
                lines.append(
                    f"| `{field_name}` | `{ftype}` | {is_req} | {fdesc} |"
                )
        else:
            lines.append("_No properties defined._")

        lines.append("")


# ============================================================
#  ENDPOINTS (by tag)
# ============================================================

def _group_paths_by_tag(spec: Dict[str, Any]):
    paths = spec.get("paths", {})
    tag_map = {}

    for path, ops in paths.items():
        for method, op in ops.items():
            if not isinstance(op, dict):
                continue
            tags = op.get("tags", ["General"])
            for tag in tags:
                tag_map.setdefault(tag, []).append({
                    "path": path,
                    "method": method.upper(),
                    "op": op,
                })
    return tag_map


def _add_endpoint_groups(lines: List[str], spec: Dict[str, Any]):
    tag_map = _group_paths_by_tag(spec)

    for tag, endpoints in tag_map.items():
        lines.append(f"## {tag}\n")

        lines.append("| Method | Path | Summary |")
        lines.append("|--------|------|---------|")

        for ep in endpoints:
            summary = ep["op"].get("summary", "")
            lines.append(
                f"| `{ep['method']}` | `{ep['path']}` | {summary} |"
            )

        lines.append("")

        for ep in endpoints:
            _add_endpoint_detail(lines, ep)


# ============================================================
#  ENDPOINT DETAIL
# ============================================================

def _add_endpoint_detail(lines: List[str], ep: Dict[str, Any]):
    path = ep["path"]
    method = ep["method"]
    op = ep["op"]

    anchor = f"{method.lower()}-{path.strip('/').replace('/', '-')}"
    lines.append(f"### {method} {path}")
    lines.append(f'<a id="{anchor}"></a>\n')

    if op.get("summary"):
        lines.append(f"**Summary:** {op['summary']}\n")

    if op.get("description"):
        lines.append(op["description"] + "\n")

    lines.append("#### Try It\n")
    lines.append("This block lets developers quickly see how a request might be made.\n")
    lines.append("```bash\ncurl -X {method} {path}\n```"
                 .replace("{method}", method)
                 .replace("{path}", path))
    lines.append("")

    _add_language_examples(lines, method, path)

    params = op.get("parameters", [])
    if params:
        lines.append("#### Parameters\n")
        lines.append("| Name | In | Type | Required | Description |")
        lines.append("|------|----|------|----------|-------------|")
        for param in params:
            pname = param.get("name", "")
            loc = param.get("in", "")
            required = "yes" if param.get("required") else "no"
            schema = param.get("schema", {})
            ptype = schema.get("type", schema.get("format", "string"))
            desc = param.get("description", "").replace("\n", " ")
            lines.append(
                f"| `{pname}` | `{loc}` | `{ptype}` | {required} | {desc} |"
            )
        lines.append("")

    _add_request_body(lines, op)
    _add_responses(lines, op)


# ============================================================
#  MULTI-LANGUAGE EXAMPLES
# ============================================================

def _add_language_examples(lines: List[str], method: str, path: str):
    url = path
    lines.append("#### Examples\n")

    lines.append("**cURL**")
    lines.append("```bash")
    lines.append(f"curl -X {method} \"{url}\"")
    lines.append("```")

    lines.append("\n**Python**")
    lines.append("```python")
    lines.append("import requests")
    lines.append(f'response = requests.{method.lower()}("{url}")')
    lines.append("print(response.json())")
    lines.append("```")

    lines.append("\n**Node.js**")
    lines.append("```javascript")
    lines.append("import fetch from 'node-fetch';")
    lines.append(f"const res = await fetch('{url}', {{ method: '{method}' }});")
    lines.append("console.log(await res.json());")
    lines.append("```")

    lines.append("\n**C#**")
    lines.append("```csharp")
    lines.append("using var client = new HttpClient();")
    lines.append(
        f'var response = await client.SendAsync(new HttpRequestMessage(HttpMethod.{method.capitalize()}, "{url}"));'
    )
    lines.append("```")

    lines.append("")


# ============================================================
# REQUEST BODY + RESPONSES
# ============================================================

def _add_request_body(lines: List[str], op: Dict[str, Any]):
    request_body = op.get("requestBody") or op.get("requestbody")
    if not request_body:
        return

    content = request_body.get("content", {})
    if not content:
        return

    lines.append("#### Request Body\n")

    for mime, media in content.items():
        lines.append(f"- **Content Type:** `{mime}`")

        schema = media.get("schema")
        if schema:
            lines.append("\nSchema:\n")
            lines.append("```json")
            lines.append(_safe_json(schema))
            lines.append("```")

        example = media.get("example")
        if example:
            lines.append("\nExample:\n")
            lines.append("```json")
            lines.append(_safe_json(example))
            lines.append("```")

        lines.append("")


def _add_responses(lines: List[str], op: Dict[str, Any]):
    responses = op.get("responses", {})
    if not responses:
        return

    lines.append("#### Responses\n")

    for status, detail in responses.items():
        desc = detail.get("description", "")
        lines.append(f"- **{status}** – {desc}\n")

        content = detail.get("content", {})
        media = content.get("application/json") or next(iter(content.values()), None)

        if media:
            example = media.get("example")
            schema = media.get("schema")

            if example:
                lines.append("Example:\n")
                lines.append("```json")
                lines.append(_safe_json(example))
                lines.append("```")

            elif schema:
                lines.append("Schema:\n")
                lines.append("```json")
                lines.append(_safe_json(schema))
                lines.append("```")

        lines.append("")


# ============================================================
# WEBHOOKS
# ============================================================

def _add_webhooks_section(lines: List[str], spec: Dict[str, Any]):
    wh = spec.get("webhooks") or spec.get("x-webhooks")
    if not wh:
        return

    lines.append("## Webhooks\n")

    for name, ops in wh.items():
        lines.append(f"### {name}\n")

        for method, op in ops.items():
            lines.append(f"**{method.upper()}**")

            if op.get("summary"):
                lines.append(f"_Summary_: {op['summary']}")
            if op.get("description"):
                lines.append(op["description"])
            lines.append("")


# ============================================================
# FALLBACK
# ============================================================

def _safe_json(obj: Any) -> str:
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False)
    except:
        return str(obj)


def _generate_generic_markdown(spec: Dict[str, Any]) -> str:
    return (
        "# API Documentation\n\n"
        "_This specification is not in a recognized OpenAPI-like format. "
        "Showing normalized JSON instead._\n\n"
        "```json\n"
        f"{_safe_json(spec)}\n"
        "```\n"
    )
