from django.urls import path

from .views import AssistantAskView


urlpatterns = [
    path("ask/", AssistantAskView.as_view(), name="assistant-ask"),
]
