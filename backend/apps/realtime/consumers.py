import json
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model
from django.utils import timezone


class RealtimeConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        query = parse_qs(self.scope.get("query_string", b"").decode())
        raw = (query.get("token") or [None])[0]
        if not raw:
            await self.close()
            return
        user = await database_sync_to_async(self._user_from_token)(raw)
        if not user:
            await self.close()
            return
        self.user = user
        await self.channel_layer.group_add("realtime", self.channel_name)
        await self.accept()
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

    async def disconnect(self, code):
        await self.channel_layer.group_discard("realtime", self.channel_name)

    async def realtime_event(self, event):
        await self.send(text_data=json.dumps({
            "event": event["event"],
            "payload": event["payload"],
            "at": event.get("at"),
        }))
