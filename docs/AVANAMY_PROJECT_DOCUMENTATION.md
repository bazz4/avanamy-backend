# Avanamy - API Documentation Generator & Monitoring Platform

**Last Updated:** December 26, 2024  
**Status:** Phase 5 Complete + Full Schema Diff + Polling Enhancements

---

## 📋 Project Overview

### Purpose
Avanamy is a SaaS platform that automatically monitors external APIs for changes, detects breaking changes, generates documentation, and sends alerts. It serves as an intelligent API documentation and monitoring system for companies that integrate with third-party APIs.

### Core Value Proposition
- **Automatic monitoring:** Poll external APIs (Stripe, DoorDash, etc.) for spec changes
- **Breaking change detection:** AI-powered diff engine identifies breaking vs non-breaking changes
- **Full schema comparison:** Side-by-side and unified diff views of complete OpenAPI specs
- **Instant alerts:** Webhook/email/Slack notifications when APIs change
- **Endpoint health monitoring:** Track availability and response times of API endpoints
- **Version history:** Complete timeline of all API changes with diffs
- **AI summaries:** Claude-generated summaries of what changed and impact
- **Generated documentation:** Auto-generate markdown and HTML docs from OpenAPI specs

### Strategic Goals
1. **Portfolio piece** for job interviews (demonstrates AI integration, production architecture)
2. **Income generation** as side business ($200-500/mo potential)
3. **Learning platform** for AI-powered SaaS development

---

## 🏗️ Architecture

### Tech Stack
- **Backend:** FastAPI (Python 3.13)
- **Frontend:** Next.js 16.1.1 (Turbopack), TypeScript, Tailwind CSS
- **Database:** PostgreSQL with UUID primary keys
- **Storage:** AWS S3 for specs and documentation
- **AI:** Anthropic Claude API (Sonnet 4) for summaries and diff analysis
- **Observability:** OpenTelemetry tracing + Prometheus metrics
- **Async:** httpx for external API calls
- **Auth:** JWT (to be implemented in Phase 4B)
- **Diff Engine:** diff library (npm) for client-side schema comparison

### Data Model Hierarchy

```
Tenant (Organization)
  └── Provider (e.g., "Stripe", "DoorDash")
      └── ApiProduct (e.g., "Payments API", "Menu API")
          └── ApiSpec (The spec being monitored)
              └── VersionHistory (v1, v2, v3...)
                  ├── DocumentationArtifacts (normalized_spec, html, markdown, original_spec per version)
                  └── Diff (breaking changes, summary)
```

### Key Design Decisions

**1. Multi-Tenant Architecture**
- Every table has `tenant_id` for isolation
- Will implement PostgreSQL Row-Level Security (RLS) in Phase 4B
- No cross-tenant data access allowed

**2. Version-Scoped Artifacts**
- Each version has its own normalized spec, markdown, HTML docs, AND original spec
- Database artifacts table has `version_history_id` FK (not just version string)
- S3 paths are version-scoped: `tenants/{tenant}/providers/{provider}/api_products/{product}/versions/{version}/specs/...`
- Enables rollback, historical viewing, and full schema comparisons

**3. Original Spec Storage (NEW - December 26, 2024)**
- Store original uploaded/polled specs separately from normalized specs
- Enables full schema comparison between any two versions
- Uses existing S3 infrastructure and documentation_artifacts table
- New artifact_type: `original_spec` (alongside `normalized_spec`, `html`, `markdown`)

**4. Watched APIs**
- `WatchedAPI` model tracks external URLs to poll
- Has direct FK to `ApiSpec` (added in Phase 5)
- Polling service fetches external specs, detects changes via SHA256 hash
- Creates new versions automatically when changes detected
- Uses UTC timestamps to prevent timezone issues

**5. Alert System (Future Notification Service)**
- `AlertConfiguration`: Where to send alerts (email, webhook, slack)
- `AlertHistory`: Audit trail of all sent alerts
- Alerts triggered by: breaking changes OR endpoint failures
- **Architecture Decision (December 26, 2024):** Notifications will be a separate module with queue-based async processing
  - Designed for easy decoupling into microservice
  - Message queue (Redis/RabbitMQ) for async notification delivery
  - Channel pattern for extensibility (Email, Slack, PagerDuty, webhooks)
  - Start as internal module, migrate to external service when scale demands

**6. Health Monitoring**
- Extracts endpoints from OpenAPI specs
- Makes actual HTTP requests to test availability
- Records status codes, response times in `EndpointHealth` table
- Alerts when endpoints start failing

---

## 📊 Database Schema

### Core Tables

**tenants**
- `id` (UUID, PK)
- `name`, `slug`
- `created_at`, `updated_at`

**providers**
- `id` (UUID, PK)
- `tenant_id` (FK)
- `name`, `slug` (e.g., "stripe", "doordash")

**api_products**
- `id` (UUID, PK)
- `tenant_id` (FK)
- `provider_id` (FK)
- `name`, `slug` (e.g., "payments-api")

**api_specs**
- `id` (UUID, PK)
- `tenant_id` (FK)
- `provider_id` (FK)
- `api_product_id` (FK)
- `name`, `version`
- `original_file_s3_path`
- `documentation_html_s3_path`

**version_history**
- `id` (Integer, PK)
- `api_spec_id` (FK)
- `version` (Integer: 1, 2, 3...)
- `diff` (JSONB: breaking changes, detailed changes)
- `summary` (Text: AI-generated summary)
- `created_at`

**documentation_artifacts**
- `id` (Integer, PK)
- `tenant_id` (FK)
- `api_spec_id` (FK)
- `version_history_id` (FK)
- `artifact_type` (enum: `normalized_spec`, `api_markdown`, `api_html`, `original_spec`) ← **Updated December 26, 2024**
- `s3_path`
- `created_at`

### Phase 4A Tables (External Polling)

**watched_apis**
- `id` (UUID, PK)
- `tenant_id` (FK)
- `provider_id` (FK)
- `api_product_id` (FK)
- `api_spec_id` (FK)
- `spec_url` (e.g., "https://api.stripe.com/openapi.yaml")
- `polling_frequency` (hourly, daily, weekly)
- `polling_enabled` (boolean)
- `last_spec_hash` (SHA256 for change detection)
- `last_polled_at`, `last_successful_poll_at` ← **Fixed to use UTC (December 26, 2024)**
- `consecutive_failures` (integer)
- `last_error` (text) - Error message from last poll failure
- `status` (active, paused, failed, deleted)

### Phase 5 Tables (Alerts & Health)

**alert_configurations**
- `id` (UUID, PK)
- `tenant_id` (FK)
- `watched_api_id` (FK)
- `alert_type` (email, webhook, slack) ← **Will become channel_type**
- `destination` (email address, webhook URL, etc.)
- `channel_config` (JSON) ← **To be added for channel-specific settings**
- `alert_on_breaking_changes` (boolean)
- `alert_on_non_breaking_changes` (boolean)
- `alert_on_endpoint_failures` (boolean)
- `alert_on_endpoint_recovery` (boolean)
- `enabled` (boolean)

**alert_history**
- `id` (UUID, PK)
- `tenant_id` (FK)
- `watched_api_id` (FK)
- `alert_config_id` (FK)
- `version_history_id` (FK, nullable)
- `alert_reason` (breaking_change, endpoint_down, endpoint_recovered)
- `severity` (info, warning, critical)
- `endpoint_path`, `http_method` (nullable, for endpoint alerts)
- `payload` (JSON: the alert content sent)
- `status` (pending, sent, failed)
- `error_message` (nullable)
- `sent_at`, `created_at`

**endpoint_health**
- `id` (UUID, PK)
- `watched_api_id` (FK)
- `endpoint_path` (e.g., "/v1/users")
- `http_method` (GET, POST, etc.)
- `status_code` (200, 401, 500, etc.)
- `response_time_ms` (integer)
- `is_healthy` (boolean: 2xx/3xx=healthy, 5xx=unhealthy)
- `error_message` (nullable)
- `checked_at` (timestamp)

---

## 🔄 Core Workflows

### 1. Manual Spec Upload
```
User uploads OpenAPI spec via Swagger UI
  → store_api_spec_file() in api_spec_service
  → Store raw spec in S3
  → Create original_spec artifact ← NEW (December 26, 2024)
  → Generate normalized spec (spec_normalizer)
  → Compute diff vs previous version (version_diff_service)
  → Detect breaking changes
  → Generate AI summary (Claude API)
  → Create VersionHistory record
  → Generate markdown docs (documentation_service)
  → Generate HTML docs
  → Store all as DocumentationArtifacts with version_history_id
```

### 2. External API Polling (Phase 4A)
```
Cron job runs poll_watched_apis.py
  → PollingService.poll_watched_api()
  → Fetch spec from external URL (httpx)
  → Compute SHA256 hash
  → Compare to last_spec_hash
  
  If changed:
    → Call update_api_spec_file() (same flow as manual upload)
    → Store original_spec artifact ← NEW (December 26, 2024)
    → Create new version
    → Check for breaking changes
    → Send alerts if configured
  
  Always (even if no change):
    → Update timestamps using UTC ← FIXED (December 26, 2024)
    → Update consecutive_failures and last_error
    → Run endpoint health checks
    → Test each endpoint with HTTP requests
    → Record results in endpoint_health table
    → Alert if endpoints failing
```

### 3. Full Schema Comparison (NEW - December 26, 2024)
```
User clicks "View Full Schema" on diff page
  → Navigate to /specs/{specId}/versions/{versionId}/full-schema
  → Fetch both versions from S3 via original_spec artifacts
  → Compare using diff library on frontend
  
  Features:
    → Search/filter within diff (highlights matches)
    → Jump to next/previous change
    → Collapsible sections (paths, components)
    → Compare ANY two versions (not just sequential)
    → Toggle unified vs split view
    → Gracefully handle missing artifacts for legacy versions
```

### 4. Alert Flow (Phase 5A - Future Enhancement)
```
Breaking change detected OR endpoint fails
  → Publish event to message queue ← NEW ARCHITECTURE (December 26, 2024)
  → NotificationWorker consumes event
  → AlertService.send_alert()
  → Query AlertConfiguration for this watched_api
  → For each config:
      → Create AlertHistory record (status=pending)
      → Route to appropriate channel:
          - EmailChannel: SMTP delivery
          - SlackChannel: Webhook (future)
          - PagerDutyChannel: API integration (future)
          - WebhookChannel: Generic HTTP POST (future)
      → Update AlertHistory (status=sent or failed)
      → Retry on failure (queue-based)
      → Increment Prometheus metrics
```

### 5. Health Monitoring (Phase 5B)
```
During polling OR on-demand:
  → EndpointHealthService.check_endpoints()
  → Parse OpenAPI spec to extract endpoints
  → For each endpoint:
      → Make HTTP request (GET, POST, etc.)
      → Record: status_code, response_time_ms, is_healthy
      → Store in endpoint_health table
      → Update Prometheus metrics
      → If newly failing:
          → Check previous health status
          → If was healthy before, send alert
```

---

## 📁 Project Structure

### Backend
```
avanamy-backend/
├── src/avanamy/
│   ├── api/routes/           # FastAPI endpoints
│   │   ├── api_specs.py      # Spec upload/management
│   │   ├── spec_versions.py  # Version history + full schema comparison
│   │   ├── spec_docs.py      # Documentation viewing
│   │   ├── watched_apis.py   # Polling management
│   │   ├── alert_configs.py  # Alert configuration CRUD
│   │   └── health.py         # Endpoint health API
│   ├── services/             # Business logic
│   │   ├── api_spec_service.py           # Main spec management
│   │   ├── original_spec_artifact_service.py  # NEW - Store original specs
│   │   ├── version_diff_service.py       # FIXED - Correct artifact lookup
│   │   ├── polling_service.py            # FIXED - UTC timestamps
│   │   ├── alert_service.py              # Alert delivery
│   │   ├── endpoint_health_service.py    # Health checks
│   │   ├── documentation_service.py      # Doc generation
│   │   └── spec_normalizer.py            # Spec normalization
│   ├── notifications/        # NEW - Future notification service (December 26, 2024)
│   │   ├── __init__.py
│   │   ├── service.py        # Main notification orchestrator
│   │   ├── channels/         # Channel implementations
│   │   │   ├── base.py       # Abstract channel interface
│   │   │   ├── email.py      # Email channel (SMTP)
│   │   │   ├── slack.py      # Slack channel (future)
│   │   │   ├── pagerduty.py  # PagerDuty channel (future)
│   │   │   └── webhook.py    # Generic webhook (future)
│   │   ├── models.py         # Notification-specific models
│   │   └── queue.py          # Message queue interface
│   ├── events/               # NEW - Event contracts for queue (December 26, 2024)
│   │   ├── __init__.py
│   │   └── contracts.py      # Shared event schemas
│   ├── models/               # SQLAlchemy models
│   ├── db/migrations/        # Alembic migrations
│   └── main.py               # FastAPI app
├── tests/                    # Comprehensive test suite
│   ├── services/
│   │   ├── test_original_spec_artifact_service.py  # NEW
│   │   ├── test_version_diff_service.py           # NEW
│   │   ├── test_api_spec_service.py               # UPDATED
│   │   └── ...
│   └── api/
│       ├── test_spec_versions.py                  # NEW - Full schema endpoints
│       └── ...
└── scripts/
    └── poll_watched_apis.py  # Cron job for polling
```

### Frontend
```
avanamy-dashboard/
├── src/
│   ├── app/
│   │   ├── specs/[specId]/versions/[versionId]/
│   │   │   ├── diff/page.tsx              # Summary diff view
│   │   │   ├── full-schema/page.tsx       # NEW - Full schema comparison
│   │   │   └── schema-diff/page.tsx       # Legacy (can be removed)
│   │   └── watched-apis/page.tsx          # UPDATED - Poll status badges
│   ├── components/
│   │   ├── DiffViewer.tsx                 # UPDATED - Expandable inline diffs
│   │   └── PollStatusBadge.tsx            # NEW - Health status indicator
│   └── lib/
│       ├── api.ts                         # API client
│       └── types.ts                       # TypeScript interfaces
└── public/
```

---

## 🆕 Recent Changes (December 26, 2024 Session)

### 1. Full Schema Comparison Feature
**Problem:** Users could only see summary diffs, not the complete spec changes.

**Solution:** Added full schema comparison with rich features:
- **Backend:** New API endpoints in `spec_versions.py`
  - `GET /api-specs/{spec_id}/versions/{version}/original-spec` - Fetch original spec from S3
  - `GET /api-specs/{spec_id}/versions/{version}/compare?compare_with={num}` - Compare any two versions
- **Frontend:** New `/full-schema` page with:
  - Unified diff view (GitHub-style)
  - Split side-by-side view
  - Search/filter functionality
  - Jump to next/previous change
  - Collapsible sections (paths, components)
  - Compare ANY two versions via dropdowns
  - Graceful handling of legacy versions without artifacts

**Files Created/Modified:**
- Backend: `original_spec_artifact_service.py`, `spec_versions.py` (2 endpoints), `api_spec_service.py` (artifact creation)
- Frontend: `full-schema/page.tsx`, `DiffViewer.tsx` (summary badge), `api.ts` (new functions)

**Tests Added:** Comprehensive unit tests via Claude Code for all backend changes

### 2. Polling Status Visibility Enhancements
**Problem:** Users couldn't see when/why polls were failing.

**Solution:** Added visual poll health indicators:
- **Frontend Component:** `PollStatusBadge.tsx`
  - Derives status from `consecutive_failures` (0 = healthy, 1-2 = warning, 3+ = failed)
  - Shows error tooltip on hover
  - Color-coded (green/yellow/red)
- **Updated:** `watched-apis/page.tsx` to display badges on each API card

**Design Decision:** No database migration needed - derive health status from existing `consecutive_failures` field

### 3. UTC Timestamp Fix
**Problem:** Poll timestamps showed "5 hours ago" when they just happened (timezone issue).

**Solution:** Fixed `polling_service.py` to use `datetime.now(timezone.utc)` instead of `datetime.now()`

**Files Modified:** `polling_service.py` (lines 218, 221)

### 4. Version Diff Service Bug Fix
**Problem:** Diff generation failed when version numbers had gaps (e.g., v1-7 exist, then v17).

**Root Cause:** Code was counting artifacts and using math to find version index, breaking when artifacts were missing.

**Solution:** Changed `_load_normalized_spec_for_version()` to:
- Look up VersionHistory by version number directly
- Find artifact by `version_history_id` FK (not by counting)
- No longer assumes sequential versions or complete artifact history

**Files Modified:** `version_diff_service.py` (lines 175-256 replaced)

### 5. Expandable Inline Diffs
**Enhancement:** Added expandable GitHub-style diffs to change cards in summary view.

**Features:**
- Click "View Details" to expand inline diff
- Shows line-by-line changes with +/- markers
- Collapsible to save space
- Summary badge showing change counts (added/removed/modified)

**Files Modified:** `DiffViewer.tsx`

### 6. Graceful Legacy Version Handling
**Problem:** Old versions don't have `original_spec` artifacts, causing 404 errors.

**Solution:** Graceful degradation in UI:
- Backend returns detailed error with `is_legacy_version` flag
- Frontend shows friendly yellow warning instead of red error
- Explains why comparison isn't available
- Provides "View Summary Diff Instead" button as alternative

**Files Modified:** 
- Backend: `spec_versions.py` (enhanced error responses)
- Frontend: `full-schema/page.tsx` (error handling and state reset)

### 7. Frontend State Management Fixes
**Problems:** 
- Stale version selections when navigating
- Attempting to compare non-existent versions

**Solutions:**
- Reset comparison state when `currentVersionId` changes
- Validate selected versions exist in available versions
- Auto-correct to nearest valid version

**Files Modified:** `full-schema/page.tsx` (2 new useEffect hooks)

### 8. Notification Service Architecture (Design Only)
**Decision:** Design notifications as queue-based async service ready for decoupling.

**Architecture:**
- Channel pattern for extensibility (Email, Slack, PagerDuty, webhooks)
- Message queue (Redis/RabbitMQ) for async delivery
- Separate `notifications/` module (same codebase initially)
- Event contracts for loose coupling
- Config-driven (can flip to external service via env var)

**Migration Path:**
- Phase 1: Internal module with queue
- Phase 2: Extract to separate microservice when scale demands
- No code changes needed - just deployment change

**Files Structure Planned:**
```
src/avanamy/notifications/
├── channels/
│   ├── base.py
│   ├── email.py
│   ├── slack.py (future)
│   └── pagerduty.py (future)
├── service.py
├── models.py
└── queue.py
```

---

## 🧪 Testing Strategy

### Test Coverage (December 26, 2024)

**New Tests Added via Claude Code:**

1. **`test_original_spec_artifact_service.py`** (NEW)
   - Tests artifact creation and linking
   - S3 path storage validation
   - Error handling
   - UUID conversion

2. **`test_version_diff_service.py`** (NEW)
   - 12 comprehensive tests
   - Critical: Version gap handling (the bug fix)
   - Diff computation validation
   - Artifact loading with FK lookup

3. **`test_api_spec_service.py`** (UPDATED)
   - Tests that `update_api_spec_file()` creates original_spec artifacts
   - Error handling for artifact storage failures
   - Validates initial uploads don't call artifact service

4. **`test_spec_versions.py`** (NEW)
   - Tests for new full schema comparison endpoints
   - GET original spec endpoint
   - GET compare endpoint
   - Tenant validation, 404 handling
   - JSON/YAML support

### Testing Philosophy
**Tier 1 (Critical):** Customer-facing flows, error handling, data integrity  
**Tier 2 (Important):** Edge cases, validation, error messages  
**Tier 3 (Nice):** Model __repr__, obscure scenarios

**Approach:** Comprehensive tests written upfront because we won't come back to add them later.

### Git Workflow
- Descriptive commit messages with context
- Squash related changes into single commits
- Reference features in commits (e.g., "feat: Full schema diff viewer with search/navigation")

---

## 📊 Observability

### Prometheus Metrics (Available)

**Alert Metrics:**
- `alerts_sent_total{alert_type, reason, severity}`
- `alerts_failed_total{alert_type, reason}`

**Endpoint Health Metrics:**
- `endpoint_health_status{watched_api_id, endpoint_path, http_method}` (1=healthy, 0=down)
- `endpoint_response_time_seconds{watched_api_id, endpoint_path, http_method}` (histogram)
- `endpoint_checks_total{watched_api_id, endpoint_path, status}` (counter)

**Future Metrics (To Add):**
- `api_changes_detected_total{watched_api_id, breaking}`
- `polling_attempts_total{watched_api_id, status}`
- `version_creation_duration_seconds{api_spec_id}`
- `notification_delivery_duration_seconds{channel_type}` ← For notification service

### OpenTelemetry Tracing
- Configured with Jaeger exporter
- Spans on all major operations:
  - `alert.send_breaking_change`
  - `alert.send_individual`
  - `health.check_endpoint`
  - `db.create_documentation_artifact`
  - `s3.upload` / `s3.download`
  - `service.store_api_spec`
  - `artifact.store_original_spec` ← NEW
  - `diff.load_normalized_spec` ← FIXED

### Logging
- Structured logging with context (tenant_id, spec_id, etc.)
- Log levels: INFO for normal ops, WARNING for issues, ERROR for failures
- **Updated (December 26, 2024):** Using `console.log` in frontend for graceful errors (not `console.error`) to avoid false "issues" badges

---

## 🔐 Security Considerations

### Current State (Pre-Auth)
- ⚠️ No authentication - anyone can access all endpoints
- ⚠️ Hardcoded tenant_id - no isolation
- ⚠️ No rate limiting on spec uploads
- ⚠️ S3 buckets should be private (verify)

### Phase 4B Will Add
- ✅ JWT authentication on all endpoints
- ✅ Tenant isolation enforced at database level (RLS)
- ✅ Rate limiting on login and API calls
- ✅ Password hashing with bcrypt
- ✅ Security headers (CORS, CSP, HSTS)
- ✅ Audit trail for sensitive operations

### Future Security Enhancements
- 2FA (TOTP-based, NOT SMS)
- API key management
- IP whitelisting for webhooks
- Encryption at rest for sensitive data
- SOC 2 compliance preparation
- **Notification security:** HMAC signatures for webhooks, encrypted channel configs

---

## 💰 Business Model (Planned)

### Pricing Tiers

**Free Tier:**
- 1 watched API
- Daily polling
- 100 endpoints monitored
- Email alerts only
- 30-day history
- Summary diffs only

**Pro Tier ($49/mo):**
- 10 watched APIs
- Hourly polling
- Unlimited endpoints
- All alert types (email, webhook, Slack)
- Unlimited history
- **Full schema comparison** ← NEW FEATURE
- API access
- Priority support

**Enterprise Tier (Custom):**
- Unlimited watched APIs
- Real-time polling
- Custom integrations (PagerDuty, etc.)
- Dedicated support
- SSO / SAML
- SLA guarantees
- On-premise option
- Custom notification channels

### Revenue Model
- Subscription-based (Stripe)
- Usage-based add-ons (extra watched APIs, more frequent polling)
- Enterprise contracts for large customers

---

## 🎓 Key Learnings

### What Worked Well (Updated December 26, 2024)
1. **Multi-tenant from day 1** - Easier than retrofitting later
2. **Version-scoped artifacts** - Enables rollback, historical viewing, and full schema diffs
3. **Comprehensive testing with Claude Code** - Catches bugs early, enables confident refactoring
4. **Direct FK relationships** - Simpler queries, clearer data model (version_history_id for artifacts)
5. **Observability from start** - OpenTelemetry + Prometheus makes debugging trivial
6. **Queue-based async design** - Sets up notification service for easy scaling
7. **Graceful degradation** - Legacy versions handled with clear messaging, not errors
8. **Client-side diff computation** - Keeps backend simple, enables rich UI features

### What Was Tricky
1. **Alembic autogenerate noise** - Required manual cleanup of every migration
2. **ApiProduct → ApiSpec relationship** - Initially indirect, caused confusion
3. **Documentation artifact versioning** - Took iteration to get right (upsert → versioned)
4. **Testing async code** - Required pytest-asyncio and careful mocking
5. **Version gap handling** - Artifact lookup by counting broke with gaps in version numbers
6. **Timezone issues** - Needed UTC timestamps for accurate "time ago" displays
7. **State management in React** - Stale selections when navigating between versions

### Design Patterns That Paid Off
1. **Service layer separation** - Business logic not in routes
2. **Repository pattern** - Database access isolated
3. **OpenTelemetry spans** - Debug production issues easily
4. **Prometheus metrics** - Real-time monitoring without logging hell
5. **S3 for artifacts** - Scales better than database for large files
6. **Channel pattern** - Easy to add new notification types
7. **Queue-based async** - Decouples slow operations (email, webhooks)
8. **Derived state** - Poll health from consecutive_failures (no migration needed)

---

## 📝 Development Notes

### Environment Setup
```bash
# Backend
cd avanamy-backend
poetry install
poetry run alembic upgrade head
poetry run uvicorn avanamy.main:app --reload

# Frontend
cd avanamy-dashboard
npm install
npm install diff @types/diff  # For full schema comparison
npm run dev

# Run tests
cd avanamy-backend
poetry run pytest tests/ -v

# Run polling script
poetry run python scripts/poll_watched_apis.py
```

### Database Access
```bash
# PostgreSQL connection
psql -h localhost -U postgres -d avanamy_dev

# Common queries
SELECT COUNT(*) FROM watched_apis;
SELECT * FROM alert_history ORDER BY created_at DESC LIMIT 10;
SELECT * FROM endpoint_health WHERE is_healthy = false;

# Check artifact types
SELECT artifact_type, COUNT(*) 
FROM documentation_artifacts 
GROUP BY artifact_type;

# Find versions missing original_spec artifacts
SELECT vh.version, vh.api_spec_id
FROM version_history vh
LEFT JOIN documentation_artifacts da 
  ON da.version_history_id = vh.id 
  AND da.artifact_type = 'original_spec'
WHERE da.id IS NULL;
```

### S3 Structure (Updated December 26, 2024)
```
avanamy-dev/
└── tenants/{tenant_id}/
    └── providers/{provider_slug}/
        └── api_products/{product_slug}/
            └── versions/{version}/
                ├── specs/{spec_id}/{filename}              # ← NEW: Original specs
                ├── normalized/{spec_id}-{slug}.json        # Normalized specs
                └── docs/
                    ├── markdown/{spec_id}-{filename}.md
                    └── html/{spec_id}-{filename}.html
```

### Useful Python Snippets
```python
# Get current tenant's watched APIs
from avanamy.db.database import SessionLocal
from avanamy.models.watched_api import WatchedAPI

db = SessionLocal()
watched = db.query(WatchedAPI).all()
for w in watched:
    print(f"{w.spec_url} -> {w.api_spec.name}")

# Trigger manual poll
from avanamy.services.polling_service import PollingService
import asyncio

polling = PollingService(db)
result = asyncio.run(polling.poll_watched_api(watched[0].id))
print(result)

# Check recent alerts
from avanamy.models.alert_history import AlertHistory

alerts = db.query(AlertHistory).order_by(AlertHistory.created_at.desc()).limit(5).all()
for alert in alerts:
    print(f"{alert.alert_reason}: {alert.status}")

# Check artifact types for a spec
from avanamy.models.documentation_artifact import DocumentationArtifact

artifacts = db.query(DocumentationArtifact).filter(
    DocumentationArtifact.api_spec_id == 'some-uuid'
).all()
for a in artifacts:
    print(f"v{a.version_history.version}: {a.artifact_type}")
```

---

## 🚀 Next Steps (Updated December 26, 2024)

### Immediate (This Week)
1. ✅ **Full schema comparison** - COMPLETE
2. ✅ **Polling status visibility** - COMPLETE
3. ✅ **UTC timestamp fix** - COMPLETE
4. ✅ **Version diff bug fix** - COMPLETE
5. ✅ **Graceful legacy handling** - COMPLETE
6. **Implement notification service**
   - Start with email channel
   - Set up message queue (Redis)
   - Design for future Slack/PagerDuty

### Near-Term (Next 2 Weeks)
7. **Complete notification channels**
   - Email (SMTP)
   - Slack webhooks
   - Generic webhook support
8. **Phase 4B (Auth)** - Build production-grade authentication
9. **Build Phase 6 (UI)** - Polish dashboard
10. **Deploy Phase 7 (Billing)** - Enable revenue generation

### Medium-Term (Next Month)
11. **Ship to beta customers** - Get real feedback
12. **Monitoring & Alerting** - Set up Prometheus + Grafana
13. **Performance optimization** - Profile and optimize slow queries
14. **Documentation** - Write user-facing docs

---

## 📞 Context for Future Conversations

**When starting a new conversation about Avanamy, share this document and add:**

1. **What phase you're working on** (e.g., "Building notification service")
2. **Specific goal** (e.g., "Implementing email channel with SMTP")
3. **Any blockers or questions** (e.g., "Should we use SendGrid or AWS SES?")
4. **Recent changes** (e.g., "Just finished full schema diff feature")

**This document should be updated after each major feature with:**
- New tables/models added
- New endpoints created
- Key design decisions made
- Known issues discovered
- Learnings and gotchas

---

## 🐛 Known Issues & Future Improvements

### Known Issues (December 26, 2024)
1. **Legacy versions** - Versions created before December 26, 2024 don't have original_spec artifacts
   - Impact: Cannot do full schema comparison on old versions
   - Solution: Gracefully handled with clear messaging
   - Future: Could backfill by re-uploading specs

2. **Poll timestamp display** - ✅ FIXED - Was showing wrong timezone
   
3. **Version gaps** - ✅ FIXED - Diff service now handles non-sequential versions

4. **Console errors on graceful failures** - ✅ FIXED - Using console.log instead of console.error

### Future Improvements
1. **Search in diffs** - Add Ctrl+F style search in full schema view
2. **Diff export** - Download diff as patch file
3. **Version comparison matrix** - Compare any N versions side-by-side
4. **Syntax highlighting** - Better JSON/YAML highlighting in diffs
5. **Performance** - Lazy load large specs, virtualize long diffs
6. **Notification templates** - Customizable alert message templates
7. **Retry logic** - Automatic retry for failed notifications
8. **Notification history UI** - Show delivery status in dashboard

---

## 📚 External Resources

### Documentation
- FastAPI: https://fastapi.tiangolo.com/
- Next.js: https://nextjs.org/docs
- SQLAlchemy: https://docs.sqlalchemy.org/
- Alembic: https://alembic.sqlalchemy.org/
- OpenTelemetry: https://opentelemetry.io/docs/languages/python/
- Prometheus: https://prometheus.io/docs/
- Tailwind CSS: https://tailwindcss.com/docs
- TypeScript: https://www.typescriptlang.org/docs/

### APIs Used
- Anthropic Claude: https://docs.anthropic.com/
- Stripe OpenAPI spec: https://github.com/stripe/openapi
- AWS S3: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html

### Tools
- Webhook testing: https://webhook.site/
- OpenAPI validator: https://apitools.dev/swagger-parser/online/
- JWT debugger: https://jwt.io/
- Diff library (npm): https://github.com/kpdecker/jsdiff

### Libraries Added (December 26, 2024)
- **diff** (npm) - Client-side diff computation
- **@types/diff** (npm) - TypeScript types for diff library

---

## 📊 Session Summary (December 26, 2024)

### What We Built
1. **Full schema comparison** with search, navigation, collapsible sections, and version selection
2. **Poll status visibility** with health badges and error tooltips
3. **Original spec storage** for enabling full schema diffs
4. **Bug fixes** for UTC timestamps and version diff lookup
5. **Graceful degradation** for legacy versions
6. **Notification service architecture** (design phase)

### Files Created
- Backend: `original_spec_artifact_service.py`
- Frontend: `full-schema/page.tsx`, `PollStatusBadge.tsx`
- Tests: `test_original_spec_artifact_service.py`, `test_version_diff_service.py`, updated `test_api_spec_service.py`, new `test_spec_versions.py`

### Files Modified
- Backend: `api_spec_service.py`, `version_diff_service.py`, `polling_service.py`, `spec_versions.py`
- Frontend: `DiffViewer.tsx`, `api.ts`, `types.ts`, `watched-apis/page.tsx`, `diff/page.tsx`

### Commits Made
- Backend: Full schema diff infrastructure, polling enhancements, bug fixes
- Frontend: Full schema viewer, poll status badges, graceful error handling
- Tests: Comprehensive coverage for all new features

### Lines of Code Added
- Backend: ~500 lines
- Frontend: ~600 lines
- Tests: ~400 lines
- **Total:** ~1,500 lines across 20+ files

### Time Investment
- **Session Duration:** ~4 hours
- **Features Shipped:** 6 major features
- **Bugs Fixed:** 4 critical bugs
- **Tests Added:** 30+ comprehensive tests

---

**End of Living Document**  
**Version:** 2.0  
**Last Updated:** December 26, 2024  
**Status:** Phase 5 Complete + Full Schema Diff + Ready for Notification Service

# Updates to Add to Avanamy Project Doc - December 27, 2025

## Section: Recent Changes

Add new section after "Recent Changes (December 26, 2024 Session)":

---

## 🆕 Recent Changes (December 27, 2025 Session - Phase 2 Complete)

### AI-Enhanced API Documentation System

**Problem:** Basic markdown docs lacked context, examples, and were hard to use.

**Solution:** Built comprehensive AI-enhanced documentation system with beautiful HTML templates:

#### 1. AI Documentation Enhancement
- **Service:** `AIDocumentationEnhancer` using Claude Sonnet 4
- **Enhancements Added:**
  - "Getting Started" section with welcome message and first API call
  - "Quick Start" with realistic examples
  - "Common Workflow" with step-by-step guidance
  - Per-endpoint "💡 Important Notes" with critical warnings
  - "Error Handling" section with best practices
  - Renames "General" sections to descriptive names (e.g., "User Management")
  
- **Cost:** ~$0.75 per spec version (one-time, cached in S3)
- **Temperature:** 0.3 for consistent, factual output
- **Max tokens:** 8000

**Files Created:**
- `src/avanamy/services/ai_documentation_enhancer.py`

**Files Modified:**
- `src/avanamy/services/documentation_service.py` - Integrated AI enhancement
- `src/avanamy/services/documentation_renderer.py` - Pass provider/product/version context
- `src/avanamy/api/routes/docs.py` - Serve raw HTML instead of JSON

#### 2. Beautiful HTML Documentation Template

**Features:**
- **Dark/Light Theme Toggle** - Matches Avanamy dashboard aesthetic
  - Dark: Sidebar (#040a1d), Content (#091124)
  - Light: White sidebar and content
  - Theme persists via localStorage
  
- **Avanamy Branding**
  - Logo in sidebar (pulse waveform A)
  - Purple/cyan gradient colors throughout
  - Favicon with Avanamy logo
  
- **Provider/Product/Version Context**
  - Breadcrumb: "TEST PROVIDER › PAYMENTS"
  - Main title: Spec name (e.g., "Test Diff Engine")
  - Dual version display:
    - Internal version badge: "📝 v9"
    - API version: "API Version 2.0.0"
  
- **Responsive Layout**
  - 260px sidebar navigation
  - Flexible content area
  - Mobile-friendly (stacks vertically)
  - Print-optimized styles
  
- **Code Styling**
  - Multi-language examples (cURL, Python, Node.js, C#)
  - Syntax highlighting with brand colors
  - Dark background in both themes
  - Proper code/text contrast
  
- **Navigation**
  - Auto-generated table of contents
  - Anchor links to sections
  - Bold top-level items (H1s)
  - Hierarchical indentation
  - Hover states with purple accent

**Design Decisions:**
- Inline code examples (not side-by-side) for simplicity
- Darker center panel in dark mode for eye comfort
- Full-width responsive (no max-width constraints)
- Compact spacing inspired by Stripe documentation

**Files Created:**
- `src/avanamy/templates/docs_base.html` - Complete rewrite with modern design

#### 3. Frontend Integration

**Approach:** Direct HTML viewing (no intermediate pages)
- "View Docs" buttons open raw HTML in new tab
- Better UX: Users can keep docs open while working in dashboard
- No style conflicts with dashboard

**Files Modified:**
- `src/app/specs/[specId]/versions/page.tsx` - Direct window.open to backend
- `src/app/specs/[specId]/versions/[versionId]/diff/page.tsx` - Same approach
- `src/lib/api.ts` - Added doc fetching functions

**Files Deleted:**
- `src/components/DocumentationViewer.tsx` - No longer needed
- `src/app/specs/[specId]/versions/[versionId]/docs/` - Entire route removed

#### 4. Backend Changes

**Public Documentation Endpoint:**
- Removed tenant authentication from docs endpoint
- Docs are public once generated (spec_id acts as secure token)
- Returns raw HTML/PlainText instead of JSON
- Added `HTMLResponse` and `PlainTextResponse` support

**Context Passing:**
- Extract spec version from OpenAPI `info.version`
- Pass provider name, product name, version label, spec version to template
- Use spec's `info.title` for H1 in content
- Use internal name for main header display

**Files Modified:**
- `src/avanamy/api/routes/docs.py` - Raw HTML serving, no auth

#### 5. CSS and Styling Details

**Color System:**
```css
/* Dark Theme */
--bg-main: #091124 (lighter content area)
--bg-sidebar: #040a1d (darker sidebar)

/* Light Theme */
--bg-main: #ffffff (white content)
--bg-sidebar: #ffffff (white sidebar)
```

**Navigation Structure:**
```
.toc > ul > ul > li > a (top level - bold)
  └── ul > li > a (nested - normal weight)
```

**Typography Hierarchy:**
1. Main title (Test Diff Engine) - 36px, gradient
2. Spec title (Test API) - 18px, gray, italic
3. Section headings - 24px, 20px with proper spacing

#### 6. AI Prompt Engineering

**Key Instructions:**
- Start with H1 using spec's exact title
- Rename "General" sections based on endpoints
- Add realistic examples with actual-looking data
- Only add "Important Notes" when truly important
- No duplicate version display
- Be concise - add value, not length

**Prompt Structure:**
```
1. Start with H1 title using "{api_title}" exactly
2. Add Getting Started section...
3. For each endpoint, add Important Notes...
4. Add Error Handling section...
5. Improve section names: rename "General"...
```

### Testing & Quality

**Pytest Fixes:**
- Fixed 3 failing tests after documentation changes
- All tests now passing
- No regressions introduced

### Commits Made

**Backend Commit:**
```
feat: Add AI-enhanced API documentation with beautiful HTML templates

- Implement Claude Sonnet 4 AI enhancement service
- Add Getting Started, Important Notes, Error Handling sections
- Create responsive HTML template with dark/light themes
- Add Provider/Product/Version context to docs
- Serve raw HTML instead of JSON
- Remove tenant auth from docs endpoint (public access)
- Pass spec version from OpenAPI schema to template

Key features:
- Dark/Light theme toggle matching dashboard
- Avanamy branding (logo, colors, favicon)
- Dual version display (internal v9 + API v2.0.0)
- Multi-language code examples
- Syntax highlighting with proper theme support
- Responsive layout
- Cost: ~$0.75 per spec version (cached in S3)
```

**Frontend Commit:**
```
feat: Streamline documentation viewing with direct HTML links

- Update 'View Docs' buttons to open HTML directly in new tab
- Remove intermediate DocumentationViewer component
- Add API functions for fetching documentation
- Clean up routing - docs open in separate window

Changes:
- View Docs buttons use window.open() to backend HTML endpoint
- Removed DocumentationViewer component
- Removed intermediate /docs route page
- Added getAvailableDocFormats() and getVersionDocumentation()
- Better UX: users can keep docs open while working
```

### Files Summary

**Backend Files Created (1):**
- `src/avanamy/services/ai_documentation_enhancer.py`

**Backend Files Modified (4):**
- `src/avanamy/services/documentation_service.py`
- `src/avanamy/services/documentation_renderer.py`
- `src/avanamy/api/routes/docs.py`
- `src/avanamy/templates/docs_base.html` (complete rewrite)

**Frontend Files Modified (3):**
- `src/lib/api.ts`
- `src/app/specs/[specId]/versions/page.tsx`
- `src/app/specs/[specId]/versions/[versionId]/diff/page.tsx`

**Frontend Files Deleted (2):**
- `src/components/DocumentationViewer.tsx`
- `src/app/specs/[specId]/versions/[versionId]/docs/page.tsx`

**Environment Variables Required:**
```bash
ANTHROPIC_API_KEY=<your-key>  # For AI enhancement
```

### Session Metrics

**Time Investment:** ~5 hours
**Features Shipped:** 1 major feature (AI-enhanced docs)
**Lines of Code:** ~1,200 lines
  - Backend: ~600 lines (AI service + HTML template)
  - Frontend: ~300 lines (updated routes)
  - Deleted: ~300 lines (removed components)

**User Experience Impact:**
- Documentation generation time: +2-3 seconds (AI enhancement)
- Documentation quality: Significantly improved
- User workflow: Simplified (no intermediate pages)
- Theme consistency: Perfect match with dashboard

---

## Update to "Next Steps" Section

### Completed This Session (December 27, 2025)
- ✅ **AI-Enhanced Documentation** - COMPLETE
  - Claude Sonnet 4 integration
  - Getting Started, Important Notes, Error Handling
  - Beautiful HTML templates with dark/light themes
  - Direct HTML viewing (no intermediate pages)

### Immediate Next Steps
1. **Breaking Change Impact Analysis** (Killer Feature - Designed)
   - AI-powered risk assessment
   - Migration guide generation
   - Rollout strategy recommendations
   - Communication templates
   - **Status:** Design complete, ready to build when prioritized

2. **Version History Page** - Add provider/product breadcrumbs
3. **Fix any remaining test failures**
4. **Documentation Polish** - Copy-code buttons, search functionality
5. **Phase 4B (Auth)** - Production authentication

---

## Update to "Key Learnings" Section

Add to "What Worked Well":
- **AI-enhanced documentation** - Claude Sonnet 4 adds tremendous value with minimal cost
- **Direct HTML serving** - Simpler than React components for static content
- **Theme toggle** - localStorage persistence provides seamless UX
- **Inline SVG logos** - No external dependencies, always available
- **Public docs endpoint** - spec_id as UUID is secure enough, simplifies access

Add to "What Was Tricky":
- **CSS selector specificity** - TOC structure (.toc > ul > ul > li > a) required precise targeting
- **Theme color matching** - Dashboard uses specific hex values that needed exact replication
- **Version display logic** - Balancing internal version (v9) vs spec version (2.0.0) clarity
- **AI prompt engineering** - Getting Claude to rename "General" consistently required explicit instructions
- **Next.js route caching** - Had to delete entire /docs directory to prevent auto-regeneration