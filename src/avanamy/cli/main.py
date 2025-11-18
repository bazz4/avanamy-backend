import uvicorn

def main():
    uvicorn.run(
        "avanamy.api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True
    )