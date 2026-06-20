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
        self.assertEqual(len(data), 49)
        self.assertTrue(data[0]["segment_id"].startswith("S"))

    def test_time_step_worker_endpoint(self):
        response = self.client.get("/api/workers?time_step=6")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data[0]["worker_id"], "WORKER_01")
        self.assertEqual(data[0]["current_segment"], "S047")

    def test_emergency_route_endpoint(self):
        response = self.client.get("/api/routes/emergency?worker_id=WORKER_01&time_step=6")

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("reachable", data)
        self.assertIn("trapped", data)
