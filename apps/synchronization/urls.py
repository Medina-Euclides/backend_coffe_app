from django.urls import path

from .views import SyncPingView, SyncPullView, SyncPushView

urlpatterns = [
    path("push/", SyncPushView.as_view(), name="sync-push"),
    path("pull/", SyncPullView.as_view(), name="sync-pull"),
    path("ping/", SyncPingView.as_view(), name="sync-ping"),
]
