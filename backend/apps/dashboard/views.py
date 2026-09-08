from rest_framework.response import Response
from rest_framework.views import APIView

from apps.dashboard import services


class OverviewView(APIView):
    def get(self, request):
        return Response(services.build_overview())


class AnalysisView(APIView):
    """总览分析聚合：summary + 图表 + 最近告警。period=day|week|month"""

    def get(self, request):
        period = request.query_params.get("period") or "day"
        return Response(services.build_analysis_payload(period))


class AlertTrendView(APIView):
    def get(self, request):
        period = request.query_params.get("period") or "day"
        return Response(services.build_alert_trend(period))


class AlertTypesView(APIView):
    def get(self, request):
        return Response(services.build_alert_types())


class AlertLevelsView(APIView):
    def get(self, request):
        return Response(services.build_alert_levels())


class CameraRankView(APIView):
    def get(self, request):
        return Response(services.build_camera_rank())


class RecentAlertsView(APIView):
    def get(self, request):
        return Response(services.build_recent_alerts())


class AreaDistributionView(APIView):
    def get(self, request):
        return Response(services.build_area_distribution())


class RealtimeDetectionsView(APIView):
    def get(self, request):
        camera_id = request.query_params.get("cameraId")
        return Response(services.build_realtime_detections(camera_id))


class ScreenView(APIView):
    """数据大屏一站式聚合。"""

    def get(self, request):
        return Response(services.build_screen_payload())
