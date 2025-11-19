from fastapi import FastAPI, UploadFile, File
from dotenv import load_dotenv

load_dotenv()  # <--- THIS LOADS .env

from avanamy.services.s3 import upload_file
import tempfile


app = FastAPI()

@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.post("/upload")
async def upload_to_s3(file: UploadFile = File(...)):
    """
    Accepts a file upload and stores it in S3.
    """

    # Save the uploaded file temporarily
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        contents = await file.read()
        tmp.write(contents)
        temp_path = tmp.name

    # Upload to S3
    s3_url = upload_file(temp_path, file.filename)

    return {
        "filename": file.filename,
        "stored_at": s3_url
    }
