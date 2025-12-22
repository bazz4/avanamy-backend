# Avanamy - API Documentation Generator & Monitoring Platform

**Last Updated:** December 22, 2024  
**Status:** Phase 5 Complete - Moving to Phase 4B (Auth) and Phase 6 (UI)

---

## 📋 Project Overview

### Purpose
Avanamy is a SaaS platform that automatically monitors external APIs for changes, detects breaking changes, generates documentation, and sends alerts. It serves as an intelligent API documentation and monitoring system for companies that integrate with third-party APIs.

### Core Value Proposition
- **Automatic monitoring:** Poll external APIs (Stripe, DoorDash, etc.) for spec changes
- **Breaking change detection:** AI-powered diff engine identifies breaking vs non-breaking changes
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
- **Database:** PostgreSQL with UUID primary keys
- **Storage:** AWS S3 for specs and documentation
- **AI:** Anthropic Claude API (Sonnet 4) for summaries and diff analysis
- **Observability:** OpenTelemetry tracing + Prometheus metrics
- **Async:** httpx for external API calls
- **Auth:** JWT (to be implemented in Phase 4B)

### Data Model Hierarchy

```
Tenant (Organization)
  └── Provider (e.g., "Stripe", "DoorDash")
      └── ApiProduct (e.g., "Payments API", "Menu API")
          └── ApiSpec (The spec being monitored)
              └── VersionHistory (v1, v2, v3...)
                  ├── DocumentationArtifacts (normalized_spec, markdown, html per version)
                  └── Diff (breaking changes, summary)
```

### Key Design Decisions

**1. Multi-Tenant Architecture**
- Every table has `tenant_id` for isolation
- Will implement PostgreSQL Row-Level Security (RLS) in Phase 4B
- No cross-tenant data access allowed

**2. Version-Scoped Artifacts**
- Each version has its own normalized spec, markdown, and HTML docs
- Database artifacts table has `version_history_id` FK (not just version string)
- S3 paths are version-scoped: `tenants/{tenant}/versions/v3/docs/html/...`
- Enables rollback, historical viewing, and version comparisons

**3. Watched APIs**
- `WatchedAPI` model tracks external URLs to poll
- Has direct FK to `ApiSpec` (added in Phase 5)
- Polling service fetches external specs, detects changes via SHA256 hash
- Creates new versions automatically when changes detected

**4. Alert System**
- `AlertConfiguration`: Where to send alerts (email, webhook, slack)
- `AlertHistory`: Audit trail of all sent alerts
- Alerts triggered by: breaking changes OR endpoint failures

**5. Health Monitoring**
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
- `version_history_id` (FK) ← NEW in Phase 5
- `artifact_type` (enum: normalized_spec, api_markdown, api_html)
- `s3_path`
- `created_at`

### Phase 4A Tables (External Polling)

**watched_apis**
- `id` (UUID, PK)
- `tenant_id` (FK)
- `provider_id` (FK)
- `api_product_id` (FK)
- `api_spec_id` (FK) ← NEW in Phase 5
- `spec_url` (e.g., "https://api.stripe.com/openapi.yaml")
- `polling_frequency` (hourly, daily, weekly)
- `polling_enabled` (boolean)
- `last_spec_hash` (SHA256 for change detection)
- `last_polled_at`, `last_successful_poll_at`
- `consecutive_failures`, `status`

### Phase 5 Tables (Alerts & Health)

**alert_configurations**
- `id` (UUID, PK)
- `tenant_id` (FK)
- `watched_api_id` (FK)
- `alert_type` (email, webhook, slack)
- `destination` (email address, webhook URL, etc.)
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
    → Create new version
    → Check for breaking changes
    → Send alerts if configured
  
  Always (even if no change):
    → Run endpoint health checks
    → Test each endpoint with HTTP requests
    → Record results in endpoint_health table
    → Alert if endpoints failing
```

### 3. Alert Flow (Phase 5A)
```
Breaking change detected OR endpoint fails
  → AlertService.send_breaking_change_alert() OR send_endpoint_failure_alert()
  → Query AlertConfiguration for this watched_api
  → For each config:
      → Create AlertHistory record (status=pending)
      → Send via appropriate channel:
          - webhook: HTTP POST with JSON payload
          - email: SMTP (mocked in MVP)
          - slack: Webhook (to be implemented)
      → Update AlertHistory (status=sent or failed)
      → Increment Prometheus metrics
```

### 4. Health Monitoring (Phase 5B)
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

```
avanamy-backend/
├── src/avanamy/
│   ├── api/routes/           # FastAPI endpoints
│   │   ├── api_specs.py      # Spec upload/management
│   │   ├── spec_versions.py  # Version history
│   │   ├── spec_docs.py      # Documentation viewing
│   │   ├── watched_apis.py   # Polling management (Phase 4A)
│   │   └── alert_configs.py  # Alert configuration (Phase 5A)
│   ├── services/             # Business logic
│   │   ├── api_spec_service.py         # Spec storage & versioning
│   │   ├── spec_normalizer.py          # OpenAPI normalization
│   │   ├── version_diff_service.py     # Diff computation
│   │   ├── documentation_service.py    # Markdown/HTML generation
│   │   ├── polling_service.py          # External API polling (Phase 4A)
│   │   ├── alert_service.py            # Alert sending (Phase 5A)
│   │   └── endpoint_health_service.py  # Health checks (Phase 5B)
│   ├── models/               # SQLAlchemy models
│   │   ├── tenant.py
│   │   ├── provider.py
│   │   ├── api_product.py
│   │   ├── api_spec.py
│   │   ├── version_history.py
│   │   ├── documentation_artifact.py
│   │   ├── watched_api.py             # Phase 4A
│   │   ├── alert_configuration.py     # Phase 5A
│   │   ├── alert_history.py           # Phase 5A
│   │   └── endpoint_health.py         # Phase 5B
│   ├── repositories/         # Database access layer
│   ├── db/
│   │   ├── database.py       # SQLAlchemy setup
│   │   └── migrations/       # Alembic migrations
│   ├── utils/
│   └── main.py               # FastAPI app entry point
├── scripts/
│   └── poll_watched_apis.py  # Cron job for polling (Phase 4A)
├── tests/                    # Unit tests
├── pyproject.toml            # Poetry dependencies
└── alembic.ini               # Database migrations config
```

---

## 🎯 Completed Phases

### ✅ Phase 1-3: Core Functionality (Pre-existing)
- Multi-tenant data model
- Spec upload and storage (S3)
- Normalized spec generation
- Version tracking
- Diff engine with breaking change detection
- AI-powered summaries (Claude API)
- Documentation generation (markdown + HTML)
- Frontend UI for viewing specs and diffs

### ✅ Phase 4A: External API Polling (Dec 2024)
**What was built:**
- `WatchedAPI` model for tracking external APIs
- `PollingService` for fetching specs and detecting changes via SHA256
- API endpoints: `/watched-apis/*` (create, list, get, poll)
- Cron script: `scripts/poll_watched_apis.py` for scheduled polling
- Automatic version creation when external specs change
- Failure tracking with auto-pause after 5 consecutive failures
- Tested with Stripe OpenAPI spec

**Files created:**
- `models/watched_api.py`
- `services/polling_service.py`
- `api/routes/watched_apis.py`
- `scripts/poll_watched_apis.py`
- Migration: `b809b5959ecf_add_watched_apis_table_for_phase_4a.py`

### ✅ Phase 5A: Breaking Change Alerts (Dec 2024)
**What was built:**
- `AlertConfiguration` model for storing alert destinations
- `AlertHistory` model for audit trail
- `AlertService` with support for email, webhook, Slack
- API endpoints: `/alert-configs/*` (CRUD + test endpoint)
- Integration with polling: sends alerts when breaking changes detected
- Prometheus metrics: `alerts_sent_total`, `alerts_failed_total`
- OpenTelemetry tracing for alert operations
- HTML-formatted alert content for emails
- JSON payload for webhooks

**Files created:**
- `models/alert_configuration.py`
- `models/alert_history.py`
- `services/alert_service.py`
- `api/routes/alert_configs.py`
- Migration: `e5e63baf3aa3_add_phase_5_alert_and_health_monitoring_tables.py`

**Testing:**
- Webhook alerts successfully sent and received
- Alert history tracking confirmed working
- Multiple alerts to same destination working

### ✅ Phase 5B: Endpoint Health Monitoring (Dec 2024)
**What was built:**
- `EndpointHealth` model for tracking endpoint status
- `EndpointHealthService` for performing health checks
- Endpoint extraction from OpenAPI specs (OpenAPI 3.x and Swagger 2.0)
- HTTP requests to test each endpoint (GET, POST, PUT, DELETE)
- Status code tracking (2xx/3xx=healthy, 5xx=unhealthy, 4xx=acceptable)
- Response time measurement in milliseconds
- Integration with polling: health checks run during every poll
- Alert on endpoint failures (new failures only, not recurring)
- Prometheus metrics: `endpoint_health_status`, `endpoint_response_time_seconds`, `endpoint_checks_total`

**Files created:**
- `models/endpoint_health.py`
- `services/endpoint_health_service.py`
- Updated `polling_service.py` to integrate health checks

**Testing:**
- Successfully monitored 20 Stripe API endpoints
- All returned 401 (auth required) correctly marked as healthy
- Health records stored in database with response times
- No false alerts on expected auth failures

### ✅ Documentation Artifact Versioning Fix (Dec 2024)
**Problem:** Documentation artifacts (markdown, HTML) were using UPSERT logic, only keeping latest version. Inconsistent with normalized specs which stored every version.

**Solution:**
- Replaced `version` string column with `version_history_id` FK
- Changed from upsert to always create new artifact rows per version
- Added version_history_id to normalized specs for consistency
- Database now maintains complete history of all artifacts per version

**Files modified:**
- `models/documentation_artifact.py`
- `services/documentation_service.py`
- `services/normalized_spec_service.py`
- `repositories/documentation_artifact_repository.py`
- Migration: `97f78c990d9f_replace_version_column_with_version_history_id_fk.py`

**Result:** Can now query "show me v3 docs" or "compare v2 vs v5 documentation"

### ✅ WatchedAPI → ApiSpec Direct FK (Dec 2024)
**Problem:** WatchedAPI had to navigate through api_product to get to api_specs, making queries complex.

**Solution:**
- Added `api_spec_id` FK directly to `WatchedAPI`
- Added `watched_apis` relationship to `ApiSpec`
- Backfilled existing WatchedAPI record
- Simplified alert code to use direct FK

**Files modified:**
- `models/watched_api.py`
- `models/api_spec.py`
- `services/polling_service.py`
- Migration: `0f38f020eedc_add_api_spec_id_fk_to_watched_apis.py`

**Result:** Cleaner queries, easier to understand data model

---

## 🚧 Upcoming Phases

### Phase 4B: User Authentication (Next - Week 1)
**Priority:** CRITICAL - Required before launch
**Effort:** 12-16 hours (2 weeks)

**Requirements:**
- Production-grade security (NOT lightweight)
- Password hashing with bcrypt
- JWT access + refresh tokens (RS256)
- Short-lived access tokens (15 min), long-lived refresh (7-30 days)
- Token rotation on refresh
- Rate limiting (10 attempts per 15 min)
- Account lockout after 5 failed attempts
- Password validation (12+ chars, complexity)
- Multi-tenant security enforcement
- PostgreSQL Row-Level Security (RLS) policies
- Session tracking (device, IP, last active)
- Login history / audit trail
- Logout from all devices
- Security headers (CORS, CSP, HSTS, etc.)

**Technologies:**
- `passlib` for password hashing
- `python-jose` for JWT
- `slowapi` for rate limiting
- PostgreSQL RLS for tenant isolation

**NO shortcuts:** Security is non-negotiable. Cost control means building it ourselves, not cutting corners.

### Phase 6: Frontend Dashboard (Week 1-2)
**Priority:** HIGH - Makes testing and validation much easier
**Effort:** 8-12 hours

**Features needed:**
- Dashboard showing all watched APIs
- Alert configuration UI (create, edit, delete alert configs)
- Health status visualizations (endpoint uptime charts)
- Version history timeline (visual diff viewer)
- Manual poll trigger button
- Alert history viewer
- Real-time health status indicators

**Why before billing:** UI will make development faster and catch bugs earlier.

### Phase 7: Billing/Stripe Integration (Week 2)
**Priority:** HIGH - Required for revenue
**Effort:** 6-8 hours

**Features:**
- Stripe subscription setup
- Usage-based pricing (track API calls, versions, endpoints monitored)
- Payment webhooks
- Plan limits (free tier, pro tier, enterprise)
- Billing portal
- Usage dashboard

### Phase 8: Embeddings & Semantic Search (Week 3)
**Priority:** MEDIUM - Differentiation feature
**Effort:** 10-15 hours

**Features:**
- Generate embeddings for endpoints and models per version
- Store vectors (options: Pinecone, pgvector, Weaviate)
- Build search APIs: "show me all endpoints dealing with orders"
- Natural language queries: "how do I create a customer?"
- Semantic similarity between API versions
- Search across all tenant's APIs

**Technical approach:**
- Use Claude API to generate embeddings
- Store in dedicated embeddings table or vector DB
- Build RAG pipeline for queries
- Cache embeddings per version (immutable)

### Phase 9: AI-Generated Guides & Examples (Week 3-4)
**Priority:** MEDIUM - High-value feature
**Effort:** 8-12 hours

**Features:**
- Generate quickstart guides per API
- Code examples for common operations (create user, place order, etc.)
- Integration tutorials (step-by-step)
- Best practices and gotchas
- Language-specific examples (Python, JavaScript, cURL)
- Store as new artifact types (alongside markdown/html)

**Technical approach:**
- Use Claude API with spec + historical change logs
- Generate on version creation
- Cache in S3 as artifacts
- Regenerate on major version changes

### Phase 10: SDK Generation (Week 4)
**Priority:** MEDIUM - High customer value
**Effort:** 12-16 hours

**Features:**
- Generate client SDKs from OpenAPI specs
- Support languages: Python, JavaScript/TypeScript, Go
- Versioned SDKs per spec version
- Download as zip or publish to package managers
- Auto-generated types/interfaces
- Error handling and retries built-in

**Technical approach:**
- Use openapi-generator or custom generator
- Store generated SDKs in S3
- Provide download links
- Consider GitHub releases for versioning

### Phase 11: Advanced RBAC (Week 5)
**Priority:** LOW - Enterprise feature
**Effort:** 8-10 hours

**Features:**
- Roles within tenant: Admin, Viewer, Integrator
- Permission system (read, write, delete per resource)
- Provider-level access control
- API key management per user
- Audit trail for permission changes

**Why later:** Not needed until enterprise customers with teams.

---

## 🐛 Known Issues & Technical Debt

### Current Issues
1. **Diff storage contains JSON `null`** for some versions instead of actual diffs
   - Older versions have `diff IS NOT NULL` but value is JSON literal `null`
   - New versions store diffs correctly
   - Not blocking but should investigate why

2. **Hardcoded tenant_id** in API endpoints
   - Currently using `11111111-1111-1111-1111-111111111111` everywhere
   - Will be replaced with JWT-based tenant extraction in Phase 4B

3. **No email sending implemented**
   - Alert service logs "would send email" but doesn't actually send
   - Need SMTP configuration or SendGrid/Postmark integration
   - Webhooks work, email is mocked

4. **No Slack integration**
   - Slack alert type exists but not implemented
   - Need Slack webhook URL support
   - Lower priority than email/webhook

### Alembic Migration Quirks
- Alembic autogenerate always detects noise (FK changes, index changes)
- Solution: Manually clean every migration file to only include intended changes
- Pattern established: Generate → Clean → Apply
- Watch out for: `ix_watched_apis_*` indexes getting dropped/recreated

### Testing Gaps (Being Filled)
- Claude Code currently writing comprehensive unit tests for Phase 5
- Need integration tests for full polling → alert flow
- Need load tests for polling at scale (100+ watched APIs)

---

## 🔧 Development Practices

### Database Migrations
**Always use Alembic, never manual SQL:**
```bash
# Generate migration
poetry run alembic revision --autogenerate -m "description"

# Clean the migration file (remove noise)
# Keep only intended changes

# Apply migration
poetry run alembic upgrade head
```

### Code Quality
- Type hints on all functions
- Docstrings for public methods
- OpenTelemetry spans for observability
- Prometheus metrics for monitoring
- Structured logging with context

### Testing Strategy
**Tier 1 (Critical):** Customer-facing flows, error handling, data integrity
**Tier 2 (Important):** Edge cases, validation, error messages
**Tier 3 (Nice):** Model __repr__, obscure scenarios

**Philosophy:** Comprehensive tests are worth it because we won't come back to add them later.

### Git Workflow
- Descriptive commit messages with context
- Squash related changes into single commits
- Reference phase numbers in commits (e.g., "feat: Phase 5A - ...")

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

### OpenTelemetry Tracing
- Configured with Jaeger exporter
- Spans on all major operations:
  - `alert.send_breaking_change`
  - `alert.send_individual`
  - `health.check_endpoint`
  - `db.create_documentation_artifact`
  - `s3.upload`
  - `service.store_api_spec`

### Logging
- Structured logging with context (tenant_id, spec_id, etc.)
- Log levels: INFO for normal ops, WARNING for issues, ERROR for failures
- Log rotation configured

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

---

## 💰 Business Model (Planned)

### Pricing Tiers

**Free Tier:**
- 1 watched API
- Daily polling
- 100 endpoints monitored
- Email alerts only
- 30-day history

**Pro Tier ($49/mo):**
- 10 watched APIs
- Hourly polling
- Unlimited endpoints
- All alert types (email, webhook, Slack)
- Unlimited history
- API access
- Priority support

**Enterprise Tier (Custom):**
- Unlimited watched APIs
- Real-time polling
- Custom integrations
- Dedicated support
- SSO / SAML
- SLA guarantees
- On-premise option

### Revenue Model
- Subscription-based (Stripe)
- Usage-based add-ons (extra watched APIs, more frequent polling)
- Enterprise contracts for large customers

---

## 🎓 Key Learnings

### What Worked Well
1. **Multi-tenant from day 1** - Easier than retrofitting later
2. **Version-scoped artifacts** - Enables rollback and historical viewing
3. **Comprehensive testing with Claude Code** - Catches bugs early, enables confident refactoring
4. **Direct FK relationships** - Simpler queries, clearer data model
5. **Observability from start** - OpenTelemetry + Prometheus makes debugging trivial

### What Was Tricky
1. **Alembic autogenerate noise** - Required manual cleanup of every migration
2. **ApiProduct → ApiSpec relationship** - Initially indirect, caused confusion
3. **Documentation artifact versioning** - Took iteration to get right (upsert → versioned)
4. **Testing async code** - Required pytest-asyncio and careful mocking

### Design Patterns That Paid Off
1. **Service layer separation** - Business logic not in routes
2. **Repository pattern** - Database access isolated
3. **OpenTelemetry spans** - Debug production issues easily
4. **Prometheus metrics** - Real-time monitoring without logging hell
5. **S3 for artifacts** - Scales better than database for large files

---

## 📝 Development Notes

### Environment Setup
```bash
# Install dependencies
poetry install

# Run migrations
poetry run alembic upgrade head

# Start backend
poetry run uvicorn avanamy.main:app --reload

# Run tests
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
```

### S3 Structure
```
avanamy-dev/
└── tenants/{tenant_id}/
    └── providers/{provider_slug}/
        └── api_products/{product_slug}/
            ├── raw/{spec_id}-{filename}
            └── versions/v{N}/
                ├── normalized/{spec_id}-{filename}.json
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
```

---

## 🚀 Next Steps (Immediate)

1. **Wait for Claude Code unit tests** (in progress)
2. **Review and run tests** - Ensure all pass
3. **Commit Phase 5** with comprehensive commit message
4. **Start Phase 4B (Auth)** - Build production-grade authentication
5. **Build Phase 6 (UI)** - Dashboard for easy testing and validation
6. **Deploy Phase 7 (Billing)** - Enable revenue generation
7. **Ship to beta customers** - Get real feedback

---

## 📞 Context for Future Conversations

**When starting a new conversation about Avanamy, share this document and add:**

1. **What phase you're working on** (e.g., "Starting Phase 4B - Auth")
2. **Specific goal** (e.g., "Need to implement JWT refresh tokens")
3. **Any blockers or questions** (e.g., "Should we use RS256 or HS256?")
4. **Recent changes** (e.g., "Just finished unit tests for Phase 5")

**This document should be updated after each major phase with:**
- New tables/models added
- New endpoints created
- Key design decisions made
- Known issues discovered
- Learnings and gotchas

---

## 📚 External Resources

### Documentation
- FastAPI: https://fastapi.tiangolo.com/
- SQLAlchemy: https://docs.sqlalchemy.org/
- Alembic: https://alembic.sqlalchemy.org/
- OpenTelemetry: https://opentelemetry.io/docs/languages/python/
- Prometheus: https://prometheus.io/docs/

### APIs Used
- Anthropic Claude: https://docs.anthropic.com/
- Stripe OpenAPI spec: https://github.com/stripe/openapi
- AWS S3: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3.html

### Tools
- Webhook testing: https://webhook.site/
- OpenAPI validator: https://apitools.dev/swagger-parser/online/
- JWT debugger: https://jwt.io/

---

**End of Living Document**  
**Version:** 1.0  
**Last Updated:** December 22, 2024  
**Status:** Phase 5 Complete, Moving to Phase 4B
