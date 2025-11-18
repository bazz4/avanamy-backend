from fastapi import FastAPI

app = FastAPI(title="Avanamy Backend")

@app.get("/health")
async def health():
    return {"status": "ok"}
