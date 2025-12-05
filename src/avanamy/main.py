from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, UploadFile, File
from avanamy.api.routes import schemas
from avanamy.api.routes.api_specs import router as api_specs_router
from avanamy.api.routes.docs import router as docs_router
import avanamy.models.tenant  # ensure models load for Alembic
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

# All API spec + docs operations are now here
app.include_router(api_specs_router)
app.include_router(docs_router)

# REMOVE THIS — no longer valid:
# app.include_router(docs_router)

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
