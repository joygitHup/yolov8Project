from django.urls import path
from .views import InferenceIngestView

urlpatterns = [
    path("ingest", InferenceIngestView.as_view()),
]
