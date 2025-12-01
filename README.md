# Avanamy Backend
Prototype backend service.

## Observability

- Tracing: OpenTelemetry spans are added across the main data path (API → parse → normalize → S3 upload → DB persist → docs generation). Tracing is configured in `src/avanamy/tracing.py` and uses a console exporter by default.
- Metrics: Existing Prometheus counters are used (`spec_upload_total`, `spec_parse_failures_total`, `markdown_generation_total`) and exposed via the Prometheus FastAPI Instrumentator.
- Logging: Logs include `trace_id` and `span_id` for easy correlation with traces. The logging configuration is in `src/avanamy/logging_config.py` and is initialized by the FastAPI entrypoint (`src/avanamy/main.py`).

Notes:
- Spans use low-cardinality attributes only (names, ids, counts) to avoid high-cardinality telemetry.
- The normalizer uses a single top-level span to avoid noisy recursive spans.

## Running tests

Run the full test suite with Poetry:

```powershell
poetry install
poetry run pytest -q
```

All tests should pass; the project includes an in-memory SQLite test setup for fast/unit tests.

## How to run the app (development)

```powershell
poetry install
poetry run uvicorn avanamy.main:app --reload
```

This will start the FastAPI app with tracing and Prometheus instrumentation enabled. The `/metrics` endpoint is exposed by the Prometheus Instrumentator.

## Changes in this branch

- Added lightweight OpenTelemetry tracing and logging across main modules:
	- `src/avanamy/services/*` (parser, normalizer, diff, s3, documentation)
	- `src/avanamy/repositories/*` (db create/read/list operations)
	- `src/avanamy/tracing.py` (tracer provider + console exporter using SimpleSpanProcessor)
	- `src/avanamy/logging_config.py` (trace-id-to-logs correlation)
- Adjusted tests and code where necessary to be compatible with observability additions.

