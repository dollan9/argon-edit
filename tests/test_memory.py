"""Test SQLite StateDB and StyleMemory vector store."""

import unittest
import tempfile
from pathlib import Path
from memory.state_db import StateDB
from memory.style_memory import StyleMemory
from agents.schemas import MediaFileAnalysis, MasterEditPlan, TimelineClipAction


class TestMemory(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_state.db"
        self.style_dir = Path(self.temp_dir.name) / "test_style"
        self.state_db = StateDB(db_path=self.db_path)
        self.style_memory = StyleMemory(persist_dir=self.style_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_state_db_lifecycle(self):
        # 1. Create project
        proj_id = self.state_db.create_project("Test Video", {"director": "Nemotron"})
        self.assertIn("proj_test_video", proj_id)

        # 2. Save media file
        analysis = MediaFileAnalysis(
            file_id="clip_01",
            master_filepath="C:/footage/master.mp4",
            proxy_filepath="C:/footage/proxy.mp4",
            fps=30.0,
            width=1920,
            height=1080,
            duration_sec=12.5,
            role="A_ROLL_MAIN",
        )
        self.state_db.save_media_file(proj_id, analysis)

        # 3. Save edit plan
        action = TimelineClipAction(
            action_id=1,
            track_type="VIDEO",
            track_index=0,
            source_file_id="clip_01",
            master_filepath="C:/footage/master.mp4",
            src_in_sec=0.0,
            src_out_sec=5.0,
            timeline_in_sec=0.0,
            reasoning="Intro clip",
        )
        plan = MasterEditPlan(
            plan_id="plan_01",
            project_title="Test Video",
            timeline_duration_sec=5.0,
            actions=[action],
        )
        self.state_db.save_edit_plan(proj_id, plan)

        # 4. Snapshots
        snap_id = self.state_db.record_snapshot(
            project_id=proj_id,
            timeline_state={"hasActiveSequence": True, "clipsCount": 1},
            plan_id="plan_01",
        )
        self.assertGreater(snap_id, 0)

        latest_snap = self.state_db.get_latest_snapshot(proj_id)
        self.assertIsNotNone(latest_snap)
        self.assertEqual(latest_snap["clipsCount"], 1)

    async def test_style_memory_rules(self):
        rule_id = await self.style_memory.add_rule(
            rule_description="Apply aggressive jump-cut punch-ins at 112% on intense speech",
            parameters={"punch_scale": 1.12, "style": "aggressive"},
            category="pacing",
        )
        self.assertTrue(rule_id.startswith("rule_"))

        # Query back
        matched = await self.style_memory.query_rules("aggressive punch-in", top_k=1)
        self.assertGreaterEqual(len(matched), 1)
        self.assertIn("aggressive", matched[0]["description"].lower())


if __name__ == "__main__":
    unittest.main()
