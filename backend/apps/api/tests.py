from django.test import SimpleTestCase


class ApiSmokeTests(SimpleTestCase):
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
        response = self.client.get("/api/workers")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 3)
        self.assertEqual(
            [(item["worker_id"], item["time_step"], item["latest_time_step"]) for item in data],
            [("WORKER_01", 0, 126), ("WORKER_02", 0, 128), ("WORKER_03", 0, 122)],
        )

    def test_workers_endpoint_time_step_zero_returns_latest_snapshots(self):
        response = self.client.get("/api/workers?time_step=0")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 3)
        self.assertTrue(all(item["snapshot_type"] == "latest_worker_snapshot" for item in data))

    def test_time_step_worker_endpoint(self):
        response = self.client.get("/api/workers?time_step=27")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 3)
        worker = next(item for item in data if item["worker_id"] == "WORKER_01")
        self.assertEqual(worker["current_segment"], "S047")
        self.assertEqual(worker["time_step"], 27)
        self.assertNotEqual(worker.get("snapshot_type"), "latest_worker_snapshot")

    def test_unknown_worker_time_step_falls_back_to_latest_snapshots(self):
        response = self.client.get("/api/workers?time_step=9999")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 3)
        self.assertTrue(all(item["time_step"] == 0 for item in data))

    def test_emergency_route_endpoint(self):
        response = self.client.get("/api/routes/emergency?worker_id=WORKER_01&time_step=6&blocked_segment=S999")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["reachable"])
        self.assertFalse(data["trapped"])
        self.assertEqual(data["route_segments"], ["S001", "S002", "S003"])
        self.assertEqual(data["cost_policy"], "length + geometry*0.15 + environmental*0.45 + worker*0.12 + tracking*0.05 + occupancy penalty")
        self.assertIn("worker_overlap_segments", data)

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

    def test_gas_sensors_endpoint_returns_recep_records(self):
        response = self.client.get("/api/gas-sensors?time_step=0")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 3)
        self.assertIn("risk_score", data[0])
        self.assertIn("gas_type", data[0])

    def test_simulation_state_returns_joined_initial_state(self):
        response = self.client.get("/api/simulation/state?time_step=0")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["time_step"], 0)
        self.assertEqual(data["counts"]["segments"], 143)
        self.assertEqual(data["counts"]["workers"], 3)
        self.assertEqual(data["counts"]["gas_sensors"], 3)
        self.assertEqual(data["source_contract"]["join_key"], "segment_id")
        self.assertEqual(
            [(item["worker_id"], item["current_segment"]) for item in data["workers"]],
            [("WORKER_01", "S001"), ("WORKER_02", "S001"), ("WORKER_03", "S001")],
        )
        s001 = next(item for item in data["segments"] if item["segment_id"] == "S001")
        self.assertEqual(s001["worker_count"], 3)
        self.assertEqual(s001["active_worker_ids"], ["WORKER_01", "WORKER_02", "WORKER_03"])

    def test_simulation_state_returns_joined_historical_state(self):
        response = self.client.get("/api/simulation/state?time_step=27")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["time_step"], 27)
        self.assertEqual(data["counts"]["segments"], 143)
        self.assertEqual(data["counts"]["workers"], 3)
        worker = next(item for item in data["workers"] if item["worker_id"] == "WORKER_01")
        self.assertEqual(worker["current_segment"], "S047")
        s047 = next(item for item in data["segments"] if item["segment_id"] == "S047")
        self.assertIn("WORKER_01", s047["active_worker_ids"])

    def test_simulation_state_holds_last_known_gas_after_gas_timeline_ends(self):
        response = self.client.get("/api/simulation/state?time_step=126")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["time_step"], 126)
        self.assertEqual(data["counts"]["workers"], 2)
        self.assertEqual(data["counts"]["gas_sensors"], 3)
        self.assertTrue(all(item["time_step"] == 89 for item in data["gas_sensors"]))
