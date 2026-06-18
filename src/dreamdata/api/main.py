"""
Dreamdata FastAPI main application.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from dreamdata.api.models import HealthResponse
from dreamdata.api.routers import (
    annotations,
    datasets,
    indexes,
    parquet,
    search,
    versions,
)

app = FastAPI(
    title="Dreamdata API",
    description="A versioned management engine for LLM training data",
    version="0.3.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(datasets.router)
app.include_router(versions.router)
app.include_router(annotations.router)
app.include_router(search.router)
app.include_router(indexes.router)
app.include_router(parquet.router)

# Mount static files for Web UI
static_path = Path(__file__).parent / "static"
if static_path.exists():
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")


@app.get("/", response_model=HealthResponse, include_in_schema=False)
async def root() -> HealthResponse:
    """Root endpoint - health check."""
    return HealthResponse(status="ok", version="0.3.0")


@app.get("/app", include_in_schema=False)
async def web_ui() -> FileResponse:
    """Web UI endpoint."""
    html_path = static_path / "index.html"
    return FileResponse(str(html_path))


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="ok", version="0.3.0")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
