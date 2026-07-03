import json

from django.conf import settings
from django.test import SimpleTestCase


class ApiSmokeTests(SimpleTestCase):
    @classmethod
    def _load_json(cls, relative_path):
        path = settings.MADENGUARD_DATA_ROOT / relative_path
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)

    @classmethod
    def _latest_workers(cls):
        return sorted(
            cls._load_json("workers/workers.json"),
            key=lambda item: item["worker_id"],
        )

    @classmethod
    def _timeline_workers(cls, time_step):
        records = cls._load_json("workers/worker_segment_timeline.json")
        return sorted(
            (item for item in records if item.get("time_step") == time_step),
            key=lambda item: item["worker_id"],
        )

    @classmethod
    def _expected_worker_pairs(cls, records):
        return [(item["worker_id"], item.get("current_segment")) for item in records]

    @classmethod
    def _anomaly_events(cls):
        payload = cls._load_json("workers/behavior_anomaly_events.json")
        return payload.get("events", [])

    def test_health_endpoint(self):
        response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

    def test_segments_endpoint_returns_normalized_ids(self):
        response = self.client.get("/api/digital-twin/segments")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 143)
        self.assertTrue(data[0]["segment_id"].startswith("S"))
        self.assertEqual(data[0]["source"], "haki_lidar")

    def test_graph_endpoint_returns_haki_segment_graph(self):
        response = self.client.get("/api/digital-twin/graph")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["nodes"]), 143)
        self.assertEqual(len(data["edges"]), 219)

    def test_pointcloud_metadata_endpoint(self):
        response = self.client.get("/api/digital-twin/pointcloud")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["preview_url"], "/static/pointcloud/tunnel_preview_500k.ply")
        self.assertEqual(data["downsampled_url"], "/static/pointcloud/tunnel_downsampled.ply")
        self.assertEqual(data["files"]["preview"]["exists"], True)
        self.assertEqual(data["files"]["downsampled"]["exists"], True)

    def test_pointcloud_static_file_is_served_by_backend(self):
        response = self.client.get("/static/pointcloud/tunnel_preview_500k.ply")

        self.assertEqual(response.status_code, 200)
        content = b"".join(response.streaming_content)
        self.assertTrue(content.startswith(b"ply"))

    def test_workers_endpoint_returns_latest_snapshots_by_default(self):
        expected = self._latest_workers()
        response = self.client.get("/api/workers")

        self.assertEqual(response.status_code, 200)
        data = sorted(response.json(), key=lambda item: item["worker_id"])
        self.assertEqual(len(data), len(expected))
        self.assertEqual([item["worker_id"] for item in data], [item["worker_id"] for item in expected])
        self.assertEqual(
            [(item["worker_id"], item["time_step"], item["latest_time_step"]) for item in data],
            [(item["worker_id"], item["time_step"], item["latest_time_step"]) for item in expected],
        )

    def test_workers_endpoint_time_step_zero_returns_latest_snapshots(self):
        expected = self._latest_workers()
        response = self.client.get("/api/workers?time_step=0")

        self.assertEqual(response.status_code, 200)
        data = sorted(response.json(), key=lambda item: item["worker_id"])
        self.assertEqual(len(data), len(expected))
        self.assertEqual([item["worker_id"] for item in data], [item["worker_id"] for item in expected])
        self.assertTrue(all(item["snapshot_type"] == "latest_worker_snapshot" for item in data))

    def test_time_step_worker_endpoint(self):
        time_step = 27
        expected = self._timeline_workers(time_step)
        response = self.client.get(f"/api/workers?time_step={time_step}")

        self.assertEqual(response.status_code, 200)
        data = sorted(response.json(), key=lambda item: item["worker_id"])
        self.assertEqual(len(data), len(expected))
        self.assertEqual(self._expected_worker_pairs(data), self._expected_worker_pairs(expected))
        self.assertTrue(all(item["time_step"] == time_step for item in data))
        self.assertTrue(all(item.get("snapshot_type") != "latest_worker_snapshot" for item in data))

    def test_unknown_worker_time_step_falls_back_to_latest_snapshots(self):
        expected = self._latest_workers()
        response = self.client.get("/api/workers?time_step=9999")

        self.assertEqual(response.status_code, 200)
        data = sorted(response.json(), key=lambda item: item["worker_id"])
        self.assertEqual(len(data), len(expected))
        self.assertEqual([item["worker_id"] for item in data], [item["worker_id"] for item in expected])
        self.assertTrue(all(item["time_step"] == 0 for item in data))

    def test_emergency_route_endpoint(self):
        time_step = 6
        worker_id = "WORKER_01"
        expected_worker = next(item for item in self._timeline_workers(time_step) if item["worker_id"] == worker_id)
        response = self.client.get(f"/api/routes/emergency?worker_id={worker_id}&time_step={time_step}&blocked_segment=S999")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["reachable"])
        self.assertFalse(data["trapped"])
        self.assertEqual(data["start_segment"], expected_worker["current_segment"])
        self.assertEqual(data["route_segments"][0], expected_worker["current_segment"])
        self.assertTrue(data["route_segments"][-1].startswith("S"))
        self.assertEqual(data["cost_policy"], "length + geometry*0.15 + environmental*0.45 + worker*0.12 + tracking*0.05 + occupancy penalty")
        self.assertIn("worker_overlap_segments", data)

    def test_emergency_route_endpoint_accepts_scenario_param(self):
        response = self.client.get("/api/routes/emergency?worker_id=WORKER_01&time_step=27&scenario=collapse_s004")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["scenario_id"], "collapse_s004")
        self.assertIn("scenario_state", data)
        self.assertEqual(data["blocked_segment"], data["scenario_state"]["blocked_segment"])
        self.assertIn("trapped", data)
        self.assertIn("route_segments", data)

    def test_emergency_route_without_scenario_uses_standard_route(self):
        response = self.client.get("/api/routes/emergency?worker_id=WORKER_01&time_step=27")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["reachable"])
        self.assertIsNone(data["blocked_segment"])
        self.assertNotIn("scenario_state", data)

    def test_emergency_route_endpoint_defaults_to_available_worker(self):
        expected_worker = self._timeline_workers(27)[0]
        response = self.client.get("/api/routes/emergency?time_step=27&blocked_segment=S999")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["worker_id"], expected_worker["worker_id"])
        self.assertEqual(data["start_segment"], expected_worker["current_segment"])

    def test_risk_endpoint_returns_current_integrated_risk(self):
        response = self.client.get("/api/risk/segments")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 143)
        self.assertIn("geometry_risk", data[0])
        self.assertIn("environmental_risk", data[0])
        self.assertIn("worker_exposure_risk", data[0])
        self.assertIn("risk_breakdown", data[0])
        self.assertEqual(data[0]["risk_breakdown"]["formula"], "0.40*geometry + 0.35*environmental + 0.20*worker + 0.05*tracking")
        self.assertAlmostEqual(
            data[0]["risk_breakdown"]["total"],
            data[0]["final_risk_score"],
            places=3,
        )

    def test_risk_endpoint_includes_multisensor_environmental_details(self):
        response = self.client.get("/api/risk/segments?time_step=0")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        sensor_segment = next(item for item in data if item["active_sensor_ids"])
        self.assertIn("environmental_measurements", sensor_segment)
        self.assertIn("environmental_component_scores", sensor_segment)
        self.assertIn("weighted_multi_sensor_risk", sensor_segment)
        self.assertIn("sensor_confidence", sensor_segment)
        self.assertIn("environmental_detail", sensor_segment["risk_breakdown"])
        self.assertIn("methane_ppm", sensor_segment["environmental_measurements"])
        self.assertIn("co_risk", sensor_segment["environmental_component_scores"])

    def test_risk_endpoint_includes_worker_behavior_anomaly_summary(self):
        first_event = self._anomaly_events()[0]
        response = self.client.get(f"/api/risk/segments?time_step={first_event['time_step']}")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        segment = next(item for item in data if item["segment_id"] == first_event["segment_id"])
        self.assertGreaterEqual(segment["behavior_event_count"], 1)
        self.assertIn(first_event["event_type"], segment["behavior_anomaly_event_types"])
        self.assertIn("behavior_anomaly", segment["risk_breakdown"])

    def test_gas_sensors_endpoint_returns_recep_records(self):
        response = self.client.get("/api/gas-sensors?time_step=0")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 3)
        self.assertIn("risk_score", data[0])
        self.assertIn("gas_type", data[0])
        self.assertEqual(data[0]["risk_score"], data[0]["environmental_risk"])
        self.assertIn("component_scores", data[0])

    def test_worker_anomalies_endpoint_filters_events(self):
        first_event = self._anomaly_events()[0]
        response = self.client.get(
            f"/api/workers/anomalies?worker_id={first_event['worker_id']}&time_step={first_event['time_step']}&event_type={first_event['event_type']}"
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(len(data), 1)
        self.assertTrue(all(item["worker_id"] == first_event["worker_id"] for item in data))
        self.assertTrue(all(item["time_step"] == first_event["time_step"] for item in data))
        self.assertTrue(all(item["event_type"] == first_event["event_type"] for item in data))

    def test_worker_anomaly_summary_endpoint(self):
        response = self.client.get("/api/workers/anomalies/summary")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["source"], "uwb_behavior_anomaly")
        self.assertEqual(data["summary"]["event_count"], len(self._anomaly_events()))

    def test_simulation_state_returns_joined_initial_state(self):
        time_step = 0
        expected_workers = self._timeline_workers(time_step)
        response = self.client.get(f"/api/simulation/state?time_step={time_step}")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["time_step"], time_step)
        self.assertEqual(data["counts"]["segments"], 143)
        self.assertEqual(data["counts"]["workers"], len(expected_workers))
        self.assertEqual(data["counts"]["gas_sensors"], 3)
        self.assertEqual(data["source_contract"]["join_key"], "segment_id")
        self.assertEqual(
            self._expected_worker_pairs(sorted(data["workers"], key=lambda item: item["worker_id"])),
            self._expected_worker_pairs(expected_workers),
        )
        expected_s001_workers = sorted(item["worker_id"] for item in expected_workers if item.get("current_segment") == "S001")
        s001 = next(item for item in data["segments"] if item["segment_id"] == "S001")
        self.assertEqual(s001["worker_count"], len(expected_s001_workers))
        self.assertEqual(s001["active_worker_ids"], expected_s001_workers)

    def test_simulation_state_returns_joined_historical_state(self):
        time_step = 27
        expected_workers = self._timeline_workers(time_step)
        response = self.client.get(f"/api/simulation/state?time_step={time_step}")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["time_step"], time_step)
        self.assertEqual(data["counts"]["segments"], 143)
        self.assertEqual(data["counts"]["workers"], len(expected_workers))
        self.assertEqual(
            self._expected_worker_pairs(sorted(data["workers"], key=lambda item: item["worker_id"])),
            self._expected_worker_pairs(expected_workers),
        )
        worker = next(item for item in data["workers"] if item["worker_id"] == "WORKER_01")
        segment = next(item for item in data["segments"] if item["segment_id"] == worker["current_segment"])
        self.assertIn("WORKER_01", segment["active_worker_ids"])

    def test_simulation_scenario_endpoint_returns_collapse_state(self):
        response = self.client.get("/api/simulation/scenario?scenario_id=collapse_s004&time_step=27")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["scenario_id"], "collapse_s004")
        self.assertEqual(data["scenario"]["blocked_segment"], "S047")
        self.assertEqual(data["scenario"]["collapse"]["blocked_segment"], "S047")
        blocked = next(item for item in data["segments"] if item["segment_id"] == "S047")
        self.assertTrue(blocked["is_blocked"])

    def test_simulation_scenario_endpoint_returns_methane_state(self):
        response = self.client.get("/api/simulation/scenario?scenario_id=methane_spike&time_step=0")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["scenario_id"], "methane_spike")
        self.assertEqual(data["scenario"]["scenario_id"], "methane_spike")
        self.assertEqual(data["scenario"]["label"], "Methane Spike")
        self.assertTrue(any(sensor.get("status") == "alarm" for sensor in data["gas_sensors"]))

    def test_simulation_scenario_worker_at_risk_accepts_selected_worker(self):
        selected_worker_id = "WORKER_05"
        response = self.client.get(f"/api/simulation/scenario?scenario_id=worker_at_risk&time_step=27&worker_id={selected_worker_id}")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["scenario"]["worker_id"], selected_worker_id)
        worker = next(item for item in data["workers"] if item["worker_id"] == selected_worker_id)
        self.assertEqual(worker["status"], "at_risk")

    def test_integration_status_endpoint_returns_contract_summary(self):
        response = self.client.get("/api/integration/status?time_step=27&scenario_id=collapse_s004")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["time_step"], 27)
        self.assertEqual(data["scenario_id"], "collapse_s004")
        self.assertEqual(data["source_contract"]["join_key"], "segment_id")
        self.assertTrue(data["checks"]["segment_contract_ok"])
        self.assertTrue(data["checks"]["join_key_contract_ok"])
        self.assertIn("shared_time_steps", data)
        self.assertGreaterEqual(data["shared_time_steps"]["count"], 1)
        self.assertIn("scenario", data)

    def test_simulation_state_holds_last_known_gas_after_gas_timeline_ends(self):
        time_step = 126
        expected_workers = self._timeline_workers(time_step)
        response = self.client.get(f"/api/simulation/state?time_step={time_step}")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["time_step"], time_step)
        self.assertEqual(data["counts"]["workers"], len(expected_workers))
        self.assertEqual(data["counts"]["gas_sensors"], 3)
        self.assertTrue(all(item["time_step"] == 89 for item in data["gas_sensors"]))

    def test_simulation_trapped_endpoint_returns_worker_list(self):
        time_step = 27
        expected_workers = self._timeline_workers(time_step)
        response = self.client.get(f"/api/simulation/trapped?time_step={time_step}")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["time_step"], time_step)
        self.assertEqual(len(data["workers"]), len(expected_workers))
        trapped_workers = [item for item in data["workers"] if item["trapped"]]
        self.assertEqual(data["summary"]["trapped_count"], len(trapped_workers))
        self.assertEqual(data["summary"]["safe_count"], len(expected_workers) - len(trapped_workers))
        self.assertEqual(data["summary"]["trapped_worker_ids"], [item["worker_id"] for item in trapped_workers])
        self.assertEqual(data["trapped_workers"], trapped_workers)

    def test_simulation_trapped_endpoint_can_return_safe_workers(self):
        time_step = 6
        expected_workers = self._timeline_workers(time_step)
        response = self.client.get(f"/api/simulation/trapped?time_step={time_step}")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        trapped_workers = [item for item in data["workers"] if item["trapped"]]
        self.assertEqual(data["summary"]["trapped_count"], len(trapped_workers))
        self.assertEqual(data["summary"]["safe_count"], len(expected_workers) - len(trapped_workers))
        self.assertEqual(data["trapped_workers"], trapped_workers)
