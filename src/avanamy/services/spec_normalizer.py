# src/avanamy/services/spec_normalizer.py

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def normalize_openapi_spec(raw_spec: dict) -> dict:
    normalized = {"paths": {}}

    paths = raw_spec.get("paths", {})

    for path in sorted(paths.keys()):
        path_item = paths[path]
        methods_out = {}

        for method in sorted(path_item.keys()):
            if method.lower() not in HTTP_METHODS:
                continue

            operation = path_item[method]

            request_required = _extract_required_fields_from_request(operation)
            response_required = _extract_required_fields_from_response(operation)

            methods_out[method.upper()] = {
                "request": {
                    "required_fields": sorted(request_required),
                },
                "response": {
                    "required_fields": sorted(response_required),
                },
            }

        if methods_out:
            normalized["paths"][path] = methods_out

    return normalized


def _extract_required_fields_from_request(operation: dict) -> list[str]:
    request_body = operation.get("requestBody", {})
    content = request_body.get("content", {})
    json_body = content.get("application/json", {})
    schema = json_body.get("schema", {})
    return schema.get("required", []) or []


def _extract_required_fields_from_response(operation: dict) -> list[str]:
    responses = operation.get("responses", {})

    # Prefer 200, else first 2xx
    status = "200" if "200" in responses else next(
        (code for code in responses if code.startswith("2")),
        None,
    )

    if not status:
        return []

    response = responses.get(status, {})
    content = response.get("content", {})
    json_body = content.get("application/json", {})
    schema = json_body.get("schema", {})
    return schema.get("required", []) or []
