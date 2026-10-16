"""Test FastMCP tool signatures, return types, and schema compliance."""

import unittest
import inspect
from pathlib import Path

from mcp_server import server
from agents.schemas import MediaAnalysisManifest, MasterEditPlan


class TestMCPTools(unittest.IsolatedAsyncioTestCase):
    def test_tool_return_annotations(self):
        import typing
        # 1. inspect_live_premiere_timeline -> Dict[str, Any]
        hints_inspect = typing.get_type_hints(server.inspect_live_premiere_timeline)
        self.assertIn("Dict", str(hints_inspect["return"]))

        # 2. ingest_and_analyze_footage -> MediaAnalysisManifest
        hints_ingest = typing.get_type_hints(server.ingest_and_analyze_footage)
        self.assertIs(hints_ingest["return"], MediaAnalysisManifest)

        # 3. generate_master_edit_plan -> MasterEditPlan
        hints_plan = typing.get_type_hints(server.generate_master_edit_plan)
        self.assertIs(hints_plan["return"], MasterEditPlan)

        # 4. execute_edit_plan_in_premiere -> Dict[str, Any]
        hints_exec = typing.get_type_hints(server.execute_edit_plan_in_premiere)
        self.assertIn("Dict", str(hints_exec["return"]))

        # 5. create_after_effects_vfx_comp -> str
        hints_vfx = typing.get_type_hints(server.create_after_effects_vfx_comp)
        self.assertIs(hints_vfx["return"], str)

        # 6. generate_photoshop_thumbnail -> str
        hints_ps = typing.get_type_hints(server.generate_photoshop_thumbnail)
        self.assertIs(hints_ps["return"], str)

        # 7. save_editing_rule_to_memory -> str
        hints_rule = typing.get_type_hints(server.save_editing_rule_to_memory)
        self.assertIs(hints_rule["return"], str)

    async def test_save_rule_returns_string_id(self):
        rule_id = await server.save_editing_rule_to_memory(
            rule_description="Always apply 108% zoom punch-in on jump cuts",
            parameters={"scale": 108.0},
        )
        self.assertIsInstance(rule_id, str)
        self.assertTrue(rule_id.startswith("rule_"))


if __name__ == "__main__":
    unittest.main()
