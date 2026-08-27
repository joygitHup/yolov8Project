from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.utils import timezone


def broadcast(event, payload):
    layer = get_channel_layer()
    if layer is None:
        return
    async_to_sync(layer.group_send)(
        "realtime",
        {
            "type": "realtime.event",
            "event": event,
            "payload": payload,
            "at": timezone.now().isoformat(),
        },
    )
