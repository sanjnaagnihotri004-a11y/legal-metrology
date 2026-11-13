from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models  # noqa: F401  (registers the tables)
from app.db import Base, engine

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Legal Metrology Compliance Checker API",
    version="1.0.0",
)

# Allow requests from any origin during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}