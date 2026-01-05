from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File
from avanamy.api.routes import schemas
from avanamy.api.routes.api_specs import router as api_specs_router
from avanamy.api.routes.docs import router as docs_router
import avanamy.models.tenant  # ensure models load for Alembic
from avanamy.api.routes.tenants import router as tenants_router
from avanamy.api.routes.providers import router as providers_router
from avanamy.api.routes.products import router as products_router
from avanamy.api.routes.spec_versions import router as spec_versions_router
from avanamy.api.routes.spec_docs import router as spec_docs_router
from avanamy.api.routes.watched_apis import router as watched_apis_router
from avanamy.api.routes.alert_configs import router as alert_configs_router
from avanamy.api.routes.alert_history import router as alert_history_router
from avanamy.api.routes.endpoint_health import router as endpoint_health_router
from avanamy.api.routes.code_repositories import router as code_repositories_router
from fastapi.middleware.cors import CORSMiddleware
from avanamy.services.s3 import upload_bytes
from avanamy.logging_config import configure_logging
from prometheus_fastapi_instrumentator import Instrumentator
from avanamy.tracing import configure_tracing
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

# ------------------------------------------------------------------
# Configure Observability
# ------------------------------------------------------------------
configure_logging()
configure_tracing()

app = FastAPI(debug=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# All API spec + docs operations are now here
app.include_router(api_specs_router)
app.include_router(docs_router)
app.include_router(providers_router)
app.include_router(tenants_router)
app.include_router(spec_versions_router)
app.include_router(products_router) 
app.include_router(spec_docs_router)
app.include_router(watched_apis_router)
app.include_router(alert_configs_router)
app.include_router(alert_history_router)
app.include_router(endpoint_health_router)
app.include_router(code_repositories_router)

# ------------------------------------------------------------------
# Observability
# ------------------------------------------------------------------
FastAPIInstrumentor.instrument_app(app)
Instrumentator().instrument(app).expose(app)

# ------------------------------------------------------------------
# Health Check
# ------------------------------------------------------------------
@app.get("/health")
def health_check():
    return {"status": "ok"}
