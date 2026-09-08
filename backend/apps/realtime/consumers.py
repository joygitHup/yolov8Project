import asyncio
import json
from http.cookies import SimpleCookie

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.accounts.authentication import ACCESS_COOKIE_NAME


def _token_from_scope(scope) -> str | None:
    """JWT from Cookie or Authorization. Query-string tokens are ignored (they leak into logs)."""
    headers = {}
    for key, value in scope.get("headers") or []:
        try:
            headers[key.decode("latin-1").lower()] = value.decode("latin-1")
        except Exception:
            continue
    auth = headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        text = auth.split(" ", 1)[1].strip()
        if text:
            return text
    jar = SimpleCookie()
    try:
        jar.load(headers.get("cookie") or "")
    except Exception:
        jar = SimpleCookie()
    morsel = jar.get(ACCESS_COOKIE_NAME)
    if morsel and morsel.value:
        return morsel.value.strip()
    return None


class RealtimeConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = None
        self._authed = False
        self._timeout_task = None
        await self.accept()
        raw = _token_from_scope(self.scope)
        if raw:
            user = await database_sync_to_async(self._user_from_token)(raw)
            if user:
                await self._bind(user)
                return
        self._timeout_task = asyncio.create_task(self._auth_timeout())

    async def _auth_timeout(self):
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            return
        if not self._authed:
            await self.close()

    async def _bind(self, user):
        self.user = user
        self._authed = True
        task = getattr(self, "_timeout_task", None)
        if task:
            task.cancel()
            self._timeout_task = None
        await self.channel_layer.group_add("realtime", self.channel_name)
        await self.send(text_data=json.dumps({
            "event": "connected",
            "user": user.username,
            "at": timezone.now().isoformat(),
        }))

    @staticmethod
    def _user_from_token(raw):
        try:
            token = AccessToken(raw)
            user = get_user_model().objects.filter(id=token["user_id"]).first()
        except Exception:
            return None
        if not user or not user.is_active:
            return None
        return user

    async def receive(self, text_data=None, bytes_data=None):
        if self._authed:
            return
        try:
            msg = json.loads(text_data or "")
        except Exception:
            await self.close()
            return
        if not isinstance(msg, dict) or msg.get("event") not in ("auth", "authenticate"):
            await self.close()
            return
        raw = str(msg.get("token") or "").strip()
        user = await database_sync_to_async(self._user_from_token)(raw) if raw else None
        if not user:
            await self.close()
            return
        await self._bind(user)

    async def disconnect(self, code):
        task = getattr(self, "_timeout_task", None)
        if task:
            task.cancel()
            self._timeout_task = None
        if getattr(self, "_authed", False):
            await self.channel_layer.group_discard("realtime", self.channel_name)

    async def realtime_event(self, event):
        if not getattr(self, "_authed", False):
            return
        await self.send(text_data=json.dumps({
            "event": event["event"],
            "payload": event["payload"],
            "at": event.get("at"),
        }))
