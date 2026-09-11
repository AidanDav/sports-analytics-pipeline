import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.api.routes.health import router as health_router

# Converts the string "INFO" from .env into logging.INFO
# Format gives timestamps, level, and which module the log came from
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

# Async context manager that handles app lifecycle
# Everything before yield runs on startup, everything after runs on shutdown
# Later this is where we'll start the scheduler and clean up resources
@asynccontextmanager
async def lifespan(application: FastAPI):
    # Startup
    logger.info("Sports Analytics Pipeline starting up")
    yield
    # Shutdown
    logger.info("Sports Analytics Pipeline shutting down")

# Factory function pattern -- makes testing easier since you can create
# fresh app instances with different configs
def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    # Browsers enforce same-origin policy. React at :5173 and API at :8000
    # are different origins. This middleware tells the browser those
    # cross-origin requests are allowed.
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.backend_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Register route groups. More include_router lines added as app grows.
    application.include_router(health_router)

    return application

app = create_app()