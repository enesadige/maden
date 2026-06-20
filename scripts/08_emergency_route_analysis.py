from __future__ import annotations

from _env import bootstrap

bootstrap()

from madenguard.config import ensure_project_dirs, load_config, project_path
from madenguard.graph_utils import adjacency_from_segments, segment_by_id, shortest_path
from madenguard.io_utils import read_json, write_json


def main() -> None:
    ensure_project_dirs()
    config = load_config()
    exit_node = str(config["runtime"].get("exit_node", "3"))
    segments = read_json(project_path("processed", "features", "segments.json"))
    workers = read_json(project_path("simulation_ready", "workers_timeline.json"))
    timeline = read_json(project_path("simulation_ready", "final_segment_risk_timeline.json"))
    critical = [row for row in timeline if row["risk_level"] == "CRITICAL"]
    event_row = sorted(critical or timeline, key=lambda item: item["final_segment_risk"], reverse=True)[0]
    is_real_emergency_threshold = bool(critical)
    blocked_segment_id = event_row["segment_id"]
    event_time = int(event_row["time_step"])
    worker = next((row for row in workers if int(row["time_step"]) == event_time), workers[min(event_time, len(workers) - 1)] if workers else None)
    worker_segment_id = worker["mapped_segment_id"] if worker else blocked_segment_id
    worker_segment = segment_by_id(segments, worker_segment_id)
    blocked_segment = segment_by_id(segments, blocked_segment_id)
    graph = adjacency_from_segments(segments, blocked_segment_id=blocked_segment_id)
    start_node = str(worker_segment["from_node"]) if worker_segment else str(blocked_segment["from_node"])
    route = shortest_path(graph, start_node, exit_node)

    if is_real_emergency_threshold:
        if worker_segment_id == blocked_segment_id:
            status = "CRITICAL_WORKER_IN_BLOCKED_SEGMENT"
            reachable = False
            route = None
        elif route:
            status = "ALTERNATIVE_ROUTE_AVAILABLE"
            reachable = True
        else:
            status = "CRITICAL_WORKER_TRAPPED"
            reachable = False
        event_type = "POTENTIAL_COLLAPSE_OR_UNSAFE_SEGMENT"
        scenario_basis = "critical_risk_threshold"
    else:
        if worker_segment_id == blocked_segment_id:
            status = "WORKER_INSIDE_HIGHEST_RISK_SEGMENT_STRESS_TEST"
            reachable = False
            route = None
        elif route:
            status = "STRESS_TEST_ALTERNATIVE_ROUTE_AVAILABLE"
            reachable = True
        else:
            status = "STRESS_TEST_NO_ROUTE_AVAILABLE"
            reachable = False
        event_type = "HIGHEST_RISK_SEGMENT_ROUTE_STRESS_TEST"
        scenario_basis = "no_critical_segment_detected_in_local_safe_pass"

    event = {
        "time_step": event_time,
        "event_type": event_type,
        "segment_id": blocked_segment_id,
        "risk_level": event_row["risk_level"],
        "final_segment_risk": event_row["final_segment_risk"],
        "reason_breakdown": event_row["reason_breakdown"],
        "scenario_basis": scenario_basis,
    }
    result = {
        "time_step": event_time,
        "worker_id": "WORKER_01",
        "worker_segment": worker_segment_id,
        "blocked_segment": blocked_segment_id,
        "exit_node": exit_node,
        "exit_reachable_after_blockage": reachable,
        "alternative_route_to_exit": route,
        "emergency_status": status,
        "scenario_basis": scenario_basis,
        "event": event,
    }
    write_json(project_path("simulation_ready", "emergency_event.json"), event)
    write_json(project_path("simulation_ready", "emergency_result.json"), result)
    report = [
        "# Emergency Scenario Report",
        "",
        f"- Event time: {event_time}",
        f"- Risk segment: {blocked_segment_id}",
        f"- Worker segment: {worker_segment_id}",
        f"- Exit node: {exit_node}",
        f"- Reachable after blockage: {reachable}",
        f"- Status: {status}",
        f"- Scenario basis: {scenario_basis}",
        f"- Alternative route: {route}",
    ]
    project_path("reports", "emergency_scenario_report.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Wrote emergency result: {status}")


if __name__ == "__main__":
    main()
