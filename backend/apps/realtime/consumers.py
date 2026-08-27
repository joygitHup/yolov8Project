import json
from urllib.parse import parse_qs
from channels.generic.websocket import WebsocketConsumer
from channels.exceptions import DenyConnection
from rest_framework_simplejwt.tokens import AccessToken
from django.contrib.auth import get_user_model


class RealtimeConsumer(WebsocketConsumer):
    def connect(self):
        query = parse_qs(self.scope.get("query_string", b"").decode())
        raw = (query.get("token") or [None])[0]
        if not raw:
            raise DenyConnection()
        try:
            token = AccessToken(raw)
            user = get_user_model().objects.filter(id=token["user_id"]).first()
        except Exception:
            raise DenyConnection()
        if not user or not user.is_active:
            raise DenyConnection()
        self.user = user
        from asgiref.sync import async_to_sync
        async_to_sync(self.channel_layer.group_add)("realtime", self.channel_name)
        self.accept()
        self.send(text_data=json.dumps({
            "event": "connected",
            "user": user.username,
            "at": __import__("django.utils.timezone", fromlist=["now"]).now().isoformat(),
        }))

    def disconnect(self, code):
        from asgiref.sync import async_to_sync
        async_to_sync(self.channel_layer.group_discard)("realtime", self.channel_name)

    def realtime_event(self, event):
        self.send(text_data=json.dumps({
            "event": event["event"],
            "payload": event["payload"],
            "at": event.get("at"),
        }))
