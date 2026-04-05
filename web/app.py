"""FastAPI application factory."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .database import init_db
from .auth import cleanup_expired_sessions


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize database and clean up expired sessions on startup."""
    init_db()
    cleanup_expired_sessions()
    yield


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Reeleezee Exporter",
        description="Export all data from Reeleezee accounting platform",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Register API routes
    from .routes.auth_routes import router as auth_router
    from .routes.admin_routes import router as admin_router
    from .routes.job_routes import router as job_router
    from .routes.data_routes import router as data_router
    from .routes.download_routes import router as download_router

    app.include_router(auth_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")
    app.include_router(job_router, prefix="/api")
    app.include_router(data_router, prefix="/api")
    app.include_router(download_router, prefix="/api")

    # Serve frontend static files
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    if os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

    return app
