from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request):
        from apps.common.rdb import ping as redis_ping
        from apps.common.storage import ping as minio_ping

        redis_ok = redis_ping()
        minio = minio_ping()
        return Response({
            "status": "ok" if redis_ok else "degraded",
            "service": "yolov8-django-backend",
            "redis": redis_ok,
            "minio": minio,
        })
