from fastapi import FastAPI

app = FastAPI(title="Avanamy Backend")

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/ping")
def ping():
    return {"status": "ok", "service": "avanamy"}