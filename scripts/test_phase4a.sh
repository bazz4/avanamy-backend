#!/bin/bash
# Test runner for Phase 4A (External API Polling)
# Excludes trio backend tests since trio is not installed

poetry run pytest \
  tests/models/test_watched_api.py \
  tests/services/test_polling_service.py \
  tests/api/test_watched_apis_routes.py \
  -k "not trio" \
  "$@"
