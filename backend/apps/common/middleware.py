from __future__ import annotations

from django.conf import settings
from django.http import HttpResponse


class SimpleCorsMiddleware:
    """Small local-dev CORS layer so Selim's Vite app can call the API."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "OPTIONS":
            response = HttpResponse(status=204)
        else:
            response = self.get_response(request)

        origin = request.headers.get("Origin")
        allowed = getattr(settings, "MADENGUARD_CORS_ORIGINS", [])
        if origin and (origin in allowed or origin.startswith("http://localhost")):
            response["Access-Control-Allow-Origin"] = origin
        elif not origin:
            response["Access-Control-Allow-Origin"] = "*"

        response["Vary"] = "Origin"
        response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
        response["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        return response
