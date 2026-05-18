"""FastAPI application entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.health import router as health_router
from app.api.v1.trips import router as trips_router
from app.api.v1.sources import router as sources_router
from app.api.v1.facts import router as facts_router

app = FastAPI(title="AI Travel Assistant", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router, prefix="/api/v1")
app.include_router(trips_router, prefix="/api/v1")
app.include_router(sources_router, prefix="/api/v1")
app.include_router(facts_router, prefix="/api/v1")
