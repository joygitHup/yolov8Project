"""DRF views that never occupy Daphne's event loop.

`as_view()` is wrapped so the sync handler runs in the ASGI thread pool
(`ASGI_THREADS`) and cannot stall WebSocket. ORM connections stay on that
worker thread.
"""
from __future__ import annotations

from asgiref.sync import markcoroutinefunction, sync_to_async
from django.db import close_old_connections
from rest_framework.views import APIView as _DRFAPIView


class APIView(_DRFAPIView):
    @classmethod
    def as_view(cls, **initkwargs):
        inner = super().as_view(**initkwargs)

        async def view(request, *args, **kwargs):
            def _run():
                close_old_connections()
                try:
                    return inner(request, *args, **kwargs)
                finally:
                    close_old_connections()

            return await sync_to_async(_run, thread_sensitive=False)()

        view.cls = cls
        view.initkwargs = initkwargs
        view.csrf_exempt = getattr(inner, "csrf_exempt", True)
        markcoroutinefunction(view)
        return view
