import json

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone


def _json_safe(value):
    return json.loads(json.dumps(value, cls=DjangoJSONEncoder))


def broadcast(event, payload):
    layer = get_channel_layer()
    if layer is None:
        return
    try:
        async_to_sync(layer.group_send)(
            "realtime",
            {
                "type": "realtime.event",
                "event": event,
                "payload": _json_safe(payload),
                "at": timezone.now().isoformat(),
            },
        )
    except Exception:
        # Never fail ingest / jobs because a websocket fan-out broke.
        import logging

        logging.getLogger("realtime").exception("broadcast %s failed", event)
