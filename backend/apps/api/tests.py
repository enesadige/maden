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
        self.assertIn("preview_url", data)
        self.assertIn("downsampled_url", data)

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
        response = self.client.get("/api/routes/emergency?worker_id=WORKER_01&time_step=6")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("reachable", data)
        self.assertIn("trapped", data)

    def test_risk_endpoint_returns_current_integrated_risk(self):
        response = self.client.get("/api/risk/segments")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 143)
        self.assertIn("geometry_risk", data[0])
        self.assertIn("environmental_risk", data[0])
        self.assertIn("worker_exposure_risk", data[0])

    def test_gas_sensors_endpoint_returns_recep_records(self):
        response = self.client.get("/api/gas-sensors?time_step=0")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data), 3)
        self.assertIn("risk_score", data[0])
        self.assertIn("gas_type", data[0])
