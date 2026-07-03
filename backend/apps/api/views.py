from __future__ import annotations

from django.conf import settings
from django.views.decorators.http import require_GET

from apps.common.http import api_response, error_response, get_time_step
from apps.common.ids import normalize_segment_id
from apps.common.json_store import available_files, data_root
from apps.lidar.services import get_graph, get_pointcloud_metadata, get_segments
from apps.risk.services import get_geometry_risk_records, get_segment_risks
from apps.routing.services import get_emergency_route
from apps.scenarios.services import get_collapse_result
from apps.sensors.services import get_environmental_risks, get_gas_sensors
from apps.simulation.services import get_integration_status, get_scenario_state, get_simulation_state, get_trapped_analysis
from apps.workers.services import get_worker_anomalies, get_worker_anomaly_summary, get_workers


@require_GET
def health(request):
    files = available_files()
    return api_response(
        {
            "status": "ok",
            "service": "madenguard-backend",
            "debug": settings.DEBUG,
            "data_root": str(data_root()),
            "json_file_count": len(files),
            "available_files": files,
        }
    )


@require_GET
def digital_twin_segments(request):
    return api_response(get_segments())


@require_GET
def digital_twin_graph(request):
    return api_response(get_graph())


@require_GET
def digital_twin_pointcloud(request):
    return api_response(get_pointcloud_metadata())


@require_GET
def workers(request):
    return api_response(get_workers(get_time_step(request)))


@require_GET
def worker_anomalies(request):
    time_step = get_time_step(request, default=None)
    return api_response(
        get_worker_anomalies(
            time_step=time_step,
            worker_id=request.GET.get("worker_id"),
            event_type=request.GET.get("event_type"),
            severity=request.GET.get("severity"),
        )
    )


@require_GET
def worker_anomaly_summary(request):
    return api_response(get_worker_anomaly_summary())


@require_GET
def risk_segments(request):
    return api_response(get_segment_risks(get_time_step(request)))


@require_GET
def geometry_risk(request):
    return api_response(get_geometry_risk_records())


@require_GET
def environmental_risk(request):
    return api_response(get_environmental_risks(get_time_step(request)))


@require_GET
def gas_sensors(request):
    return api_response(get_gas_sensors(get_time_step(request)))


@require_GET
def simulation_state(request):
    return api_response(get_simulation_state(get_time_step(request, default=0)))


@require_GET
def simulation_trapped(request):
    return api_response(get_trapped_analysis(get_time_step(request, default=0)))


@require_GET
def simulation_scenario(request):
    scenario_id = request.GET.get("scenario_id") or request.GET.get("scenario") or "normal"
    worker_id = request.GET.get("worker_id")
    return api_response(get_scenario_state(scenario_id, get_time_step(request, default=0), worker_id=worker_id))


@require_GET
def integration_status(request):
    scenario_id = request.GET.get("scenario_id") or request.GET.get("scenario")
    worker_id = request.GET.get("worker_id")
    return api_response(get_integration_status(get_time_step(request, default=0), scenario_id=scenario_id, worker_id=worker_id))


@require_GET
def collapse_scenario(request):
    return api_response(get_collapse_result())


@require_GET
def emergency_route(request):
    time_step = get_time_step(request)
    requested_worker_id = request.GET.get("worker_id")
    worker_id = requested_worker_id
    exit_node = request.GET.get("exit_node", "3")
    scenario_id = request.GET.get("scenario")

    collapse = get_collapse_result()
    start_segment = request.GET.get("segment_id")
    if not start_segment:
        workers_at_time = get_workers(time_step)
        if requested_worker_id:
            matching_workers = [item for item in workers_at_time if item.get("worker_id") == requested_worker_id]
            if not matching_workers:
                return error_response("worker_not_found", status=404, worker_id=requested_worker_id, time_step=time_step)
            selected_worker = matching_workers[0]
        else:
            if not workers_at_time:
                return error_response("worker_not_found", status=404, worker_id=None, time_step=time_step)
            selected_worker = workers_at_time[0]
        worker_id = selected_worker.get("worker_id")
        start_segment = selected_worker.get("current_segment")

    scenario_state = get_scenario_state(scenario_id, time_step, worker_id=worker_id) if scenario_id else None
    scenario_blocked_segment = scenario_state.get("scenario", {}).get("blocked_segment") if scenario_state else None
    blocked_segment = request.GET.get("blocked_segment") or scenario_blocked_segment or collapse.get("blocked_segment")

    route = get_emergency_route(
        start_segment=normalize_segment_id(start_segment),
        exit_node=exit_node,
        blocked_segment=blocked_segment,
        worker_id=worker_id,
        time_step=time_step,
    )
    route["worker_id"] = worker_id
    route["affected_workers"] = [worker_id] if worker_id else []
    route["time_step"] = time_step
    if scenario_state:
        route["scenario_id"] = scenario_state.get("scenario_id")
        route["scenario_state"] = scenario_state.get("scenario")
    return api_response(route)
