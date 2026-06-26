from django.conf import settings
from django.urls import include, path
from django.views.static import serve


urlpatterns = [
    path("api/", include("apps.api.urls")),
    path(
        "static/pointcloud/<path:path>",
        serve,
        {"document_root": settings.MADENGUARD_DATA_ROOT / "haki_lidar" / "pointcloud"},
        name="pointcloud_static",
    ),
]
