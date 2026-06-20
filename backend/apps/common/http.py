from __future__ import annotations

from typing import Any

from django.http import JsonResponse


def get_time_step(request, default: int | None = 0) -> int | None:
    raw = request.GET.get("time_step")
    if raw is None or raw == "":
        return default
    if raw.lower() == "all":
        return None
    return int(raw)


def api_response(data: Any, status: int = 200) -> JsonResponse:
    return JsonResponse(data, safe=not isinstance(data, list), status=status)


def error_response(message: str, status: int = 400, **extra: Any) -> JsonResponse:
    payload = {"error": message}
    payload.update(extra)
    return JsonResponse(payload, status=status)
