"""Test Mock Adobe CEP server and end-to-end bridge communication."""

import unittest
import httpx
from tests.mock_adobe_server import MockAdobeCluster
from main_orchestrator import SelfHealingExecutor
from mcp_server.server import inspect_live_premiere_timeline


class TestMockAdobeCluster(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.cluster = MockAdobeCluster([8088, 8089, 8090])
        cls.cluster.start()

    @classmethod
    def tearDownClass(cls):
        cls.cluster.stop()

    async def test_health_endpoints(self):
        async with httpx.AsyncClient(timeout=5.0) as client:
            for port, expected_app in [(8088, "PPRO"), (8089, "AEFT"), (8090, "PHXS")]:
                resp = await client.get(f"http://127.0.0.1:{port}/health")
                self.assertEqual(resp.status_code, 200)
                data = resp.json()
                self.assertEqual(data["status"], "ok")
                self.assertEqual(data["appId"], expected_app)
                self.assertTrue(data.get("mock"))

    async def test_timeline_state_query(self):
        executor = SelfHealingExecutor(bridge_url="http://127.0.0.1:8088")
        state = await executor.get_live_timeline_state()
        self.assertEqual(state.get("status"), "ok")
        self.assertEqual(state.get("sequenceName"), "Mock_Master_Timeline")
        self.assertEqual(len(state.get("videoTracks", [])), 3)

    async def test_mcp_inspect_tool_against_mock(self):
        res = await inspect_live_premiere_timeline()
        self.assertEqual(res.get("status"), "ok")
        timeline = res.get("timeline_state", {})
        self.assertEqual(timeline.get("sequenceName"), "Mock_Master_Timeline")


if __name__ == "__main__":
    unittest.main()
