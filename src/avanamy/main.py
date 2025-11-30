from dotenv import load_dotenv
load_dotenv()  # <--- THIS LOADS .env

from fastapi import FastAPI, UploadFile, File
from avanamy.api.routes import schemas  # package import
from avanamy.api.routes.api_specs import router as api_specs_router
from avanamy.api.routes.docs import router as docs_router
from avanamy.services.s3 import upload_bytes
import tempfile


app = FastAPI(debug=True)

app.include_router(schemas.router, prefix="/schemas", tags=["Schemas"])
app.include_router(api_specs_router) 
app.include_router(docs_router)

@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/upload")
async def upload_to_s3(file: UploadFile = File(...)):
    """
    Accepts a file upload and stores it in S3.
    """
    # Read file contents as bytes
    contents = await file.read()

    # Build a simple S3 key and upload bytes; upload_bytes returns (key, s3_url)
    key = f"uploads/{file.filename}"
    _, s3_url = upload_bytes(key, contents, content_type=getattr(file, "content_type", None))

    return {
        "filename": file.filename,
        "stored_at": s3_url,
    }
