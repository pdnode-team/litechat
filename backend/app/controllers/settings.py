"""Administrator-editable runtime settings (SMTP + notification policy)."""
from typing import Any, Dict

from litestar import Controller, get, post, put, Request
from litestar.exceptions import NotAuthorizedException, PermissionDeniedException

from app.controllers.auth import get_current_user_from_request
from app.schemas.settings import (
    EmailSettingsUpdate,
    NotificationSettingsUpdate,
    TestEmailRequest,
    TestEmailResult,
)
from app.services import email_service, settings_service


class SettingsController(Controller):
    path = "/api/settings"

    async def _require_admin(self, request: Request):
        current_user = await get_current_user_from_request(request)
        if not current_user:
            raise NotAuthorizedException("Authentication required.")
        if current_user.role != "admin":
            raise PermissionDeniedException("Forbidden: Administrator privileges required.")
        return current_user

    @get("/")
    async def get_settings(self, request: Request) -> Dict[str, Any]:
        """Current settings. The SMTP password is reported as set/unset only."""
        await self._require_admin(request)
        values = await settings_service.get_all(force=True)
        return settings_service.public_view(values)

    @put("/email")
    async def update_email_settings(self, request: Request, data: EmailSettingsUpdate) -> Dict[str, Any]:
        await self._require_admin(request)
        await settings_service.set_many(data.model_dump(exclude_unset=True))
        return settings_service.public_view(await settings_service.get_all())

    @put("/notifications")
    async def update_notification_settings(
        self, request: Request, data: NotificationSettingsUpdate
    ) -> Dict[str, Any]:
        await self._require_admin(request)
        await settings_service.set_many(data.model_dump(exclude_unset=True))
        return settings_service.public_view(await settings_service.get_all())

    @post("/email/test")
    async def send_test_email(self, request: Request, data: TestEmailRequest) -> TestEmailResult:
        await self._require_admin(request)
        sent, detail = await email_service.send_test_email(data.to)
        return TestEmailResult(sent=sent, detail=detail)
