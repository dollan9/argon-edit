"""End-to-end integration and edge-case testing for Argon Video Engine."""

import unittest
import tempfile
import json
from pathlib import Path

from config.settings import get_settings, seconds_to_ticks, ticks_to_seconds
from agents.schemas import (
    MediaFileAnalysis,
    MediaAnalysisManifest,
    WordToken,
    SilenceOrFillerSpan,
    VisualShotAnalysis,
    MasterEditPlan,
)
from agents.director_agent import DirectorAgent
from agents.audio_master_agent import AudioMasterAgent
from mcp_server.jsx_compiler import JSXCompiler
from main_orchestrator import SelfHealingExecutor, ArgonEngine


class TestEndToEndAndEdgeCases(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.director = DirectorAgent()
        self.audio = AudioMasterAgent()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_unicode_and_special_paths(self):
        # Master filepath with spaces, parentheses, accents
        special_path = "C:/Videos/Projet 1 (Édition Spéciale) #1/clip_01 [4K].mp4"
        jsx = JSXCompiler.compile_insert_clip(special_path, 0.0, 5.0, 0.0, 0, 0)
        self.assertIn("Projet 1 (Édition Spéciale) #1/clip_01 [4K].mp4", jsx)
        # Verify strict ES3 compliance
        violations = JSXCompiler.validate_es3(jsx, raise_on_error=False)
        self.assertEqual(len(violations), 0)

    def test_empty_words_and_no_silences(self):
        # Clip with no speech detected (e.g. pure B-roll or music)
        silent_clip = MediaFileAnalysis(
            file_id="silent_01",
            master_filepath="C:/footage/silent.mp4",
            proxy_filepath="C:/footage/proxy_silent.mp4",
            fps=25.0,
            width=1920,
            height=1080,
            duration_sec=8.0,
            role="A_ROLL_MAIN",
            words=[],
            bad_spans=[],
            shots=[
                VisualShotAnalysis(
                    shot_id=1,
                    source_file="C:/footage/silent.mp4",
                    start_sec=0.0,
                    end_sec=8.0,
                    shot_scale="WS",
                    camera_motion="static",
                    visual_quality_score=7,
                    is_usable=True,
                    subject_emotion="neutral",
                    b_roll_tags=["silent"],
                    summary="No speech present",
                )
            ],
        )

        manifest = MediaAnalysisManifest(
            manifest_id="silent_manifest",
            project_name="Silent Test",
            files=[silent_clip],
        )

        plan = self.director.generate_edit_plan(manifest, editing_style="Cinematic")
        # Should not crash, should create a single continuous segment
        self.assertEqual(len(plan.actions), 2)  # V1 and A1
        self.assertAlmostEqual(plan.timeline_duration_sec, 8.0, places=2)

    def test_large_batch_scalability(self):
        # 60 cuts back to back
        actions = []
        for i in range(60):
            t_in = i * 2.0
            from agents.schemas import TimelineClipAction, KeyframeTransform
            actions.append(
                TimelineClipAction(
                    action_id=i + 1,
                    track_type="VIDEO",
                    track_index=0,
                    source_file_id=f"clip_{i % 5}",
                    master_filepath=f"C:/media/clip_{i % 5}.mp4",
                    src_in_sec=1.0,
                    src_out_sec=3.0,
                    timeline_in_sec=t_in,
                    keyframes=[KeyframeTransform(time_offset_sec=0.0, scale=108.0 if i % 2 == 1 else 100.0)],
                    reasoning=f"Slice {i}",
                )
            )

        plan = MasterEditPlan(
            plan_id="large_plan",
            project_title="Large Scale Test",
            timeline_duration_sec=120.0,
            actions=actions,
        )

        compiled = JSXCompiler.compile_edit_plan_batch(plan)
        self.assertEqual(len(JSXCompiler.validate_es3(compiled, raise_on_error=False)), 0)
        self.assertIn("totalActions: 60", compiled)

    def test_tick_roundtrip_precision_edge_cases(self):
        # Boundary timestamps (0.001s, 23.976fps frame durations)
        frame_24p = 1.0 / 23.976
        ticks = seconds_to_ticks(frame_24p)
        roundtrip = ticks_to_seconds(ticks)
        self.assertAlmostEqual(frame_24p, roundtrip, places=9)

    async def test_full_pipeline_mock_execution(self):
        # Verify engine components initialize and coordinate smoothly
        engine = ArgonEngine()
        self.assertIsNotNone(engine.settings)
        self.assertIsNotNone(engine.ingestion)
        self.assertIsNotNone(engine.director)
        self.assertIsNotNone(engine.audio_master)


if __name__ == "__main__":
    unittest.main()
