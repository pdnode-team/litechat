import logging
from litestar import Litestar, get
from litestar.config.cors import CORSConfig
from litestar.static_files import create_static_files_router
from litestar.openapi.config import OpenAPIConfig

from app.config import UPLOAD_DIR
from app.db.session import init_db
from app.db.seed import seed_initial_data
from app.controllers.auth import AuthController
from app.controllers.tickets import TicketController
from app.controllers.messages import MessageController, UploadController
from app.controllers.canned_responses import CannedResponseController
from app.controllers.csat import CSATController
from app.controllers.analytics import AnalyticsController
from app.controllers.users import UserController
from app.controllers.managed_apps import ManagedAppController
from app.controllers.ticket_types import TicketTypeController
from app.controllers.faq import FaqController
from app.controllers.websocket import ticket_websocket_handler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("litechat")

async def on_app_startup() -> None:
    logger.info("Initializing database schemas...")
    await init_db()
    logger.info("Seeding initial administrator...")
    await seed_initial_data()
    logger.info("LiteChat backend ready!")

import os

allowed_origins_raw = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,http://localhost:5173,http://127.0.0.1:5173",
)
allowed_origins = [o.strip() for o in allowed_origins_raw.split(",") if o.strip()]

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

openapi_config = OpenAPIConfig(
    title="LiteChat Support Hub API",
    version="1.0.0",
    path="/schema",
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
        ticket_websocket_handler,
        static_files_router,
    ],
    cors_config=cors_config,
    on_startup=[on_app_startup],
    openapi_config=openapi_config,
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
