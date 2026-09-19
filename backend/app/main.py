import logging
import os

from litestar import Litestar, get
from litestar.config.cors import CORSConfig
from litestar.openapi.config import OpenAPIConfig
from litestar.static_files import create_static_files_router

from app.config import ENABLE_API_DOCS, IS_PRODUCTION, UPLOAD_DIR
from app.controllers.analytics import AnalyticsController
from app.controllers.auth import AuthController
from app.controllers.canned_responses import CannedResponseController
from app.controllers.csat import CSATController
from app.controllers.faq import FaqController
from app.controllers.managed_apps import ManagedAppController
from app.controllers.messages import MessageController, UploadController
from app.controllers.settings import SettingsController
from app.controllers.ticket_types import TicketTypeController
from app.controllers.tickets import TicketController
from app.controllers.users import UserController
from app.controllers.websocket import (
    notifications_websocket_handler,
    ticket_websocket_handler,
)
from app.db.seed import seed_initial_data
from app.db.session import init_db
from app.middleware import RateLimitMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("litechat")


async def on_app_startup() -> None:
    logger.info("Initializing database schemas...")
    await init_db()
    if os.getenv("ADMIN_EMAIL") and os.getenv("ADMIN_PASSWORD"):
        logger.info("Seeding initial administrator from environment...")
        await seed_initial_data()
    if IS_PRODUCTION:
        logger.info("Environment: production")
    logger.info("LiteChat backend ready!")


allowed_origins_raw = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
)
allowed_origins = [origin.strip() for origin in allowed_origins_raw.split(",") if origin.strip()]

cors_config = CORSConfig(
    allow_origins=allowed_origins,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    allow_credentials=True,
)

static_files_router = create_static_files_router(
    path="/api/files",
    directories=[UPLOAD_DIR],
)

# The schema exposes every route, parameter and model. Useful in development,
# so it is disabled in production unless ENABLE_API_DOCS=true is set.
openapi_config = (
    OpenAPIConfig(
        title="LiteChat Support Hub API",
        version="1.0.0",
        path="/schema",
    )
    if ENABLE_API_DOCS
    else None
)


@get("/api/health")
async def health_check() -> dict:
    return {"status": "ok", "service": "LiteChat"}


app = Litestar(
    route_handlers=[
        health_check,
        AuthController,
        TicketController,
        MessageController,
        UploadController,
        CannedResponseController,
        CSATController,
        AnalyticsController,
        UserController,
        ManagedAppController,
        TicketTypeController,
        FaqController,
        SettingsController,
        ticket_websocket_handler,
        notifications_websocket_handler,
        static_files_router,
    ],
    cors_config=cors_config,
    middleware=[RateLimitMiddleware],
    on_startup=[on_app_startup],
    openapi_config=openapi_config,
)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
