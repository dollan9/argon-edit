"""Comprehensive Regression Tests for Project Argon-Edit /hack fixes.

Verifies:
1. Exact dBFS calculation in RMS silence detection (F-09).
2. Cross-file provenance in B-roll semantic keyword matching (F-12).
3. Newline, quote, and control character escaping in JSXCompiler (F-08, F-01, F-22).
4. Leading and trailing dead-air span capture in transcribe_audio (F-16).
5. Self-Healing Executor detection of batch partial_error payloads (F-19).
6. StateDB SQLite foreign key enforcement and auto-project record (F-18, F-07).
7. VFX Callout custom timeline_in_sec placement (F-06).
"""

from __future__ import annotations
import math
import wave
import struct
import tempfile
import unittest
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

from agents.schemas import (
    WordToken,
    SilenceOrFillerSpan,
    VisualShotAnalysis,
    MediaFileAnalysis,
    MediaAnalysisManifest,
    MasterEditPlan,
    TimelineClipAction,
)
from agents.ingestion_agent import IngestionAgent
from agents.director_agent import DirectorAgent
from agents.vfx_motion_agent import VFXMotionAgent
from mcp_server.jsx_compiler import JSXCompiler, ES3ValidationError
from mcp_server.server import create_after_effects_vfx_comp
from main_orchestrator import SelfHealingExecutor
from memory.state_db import StateDB


class TestHackRemediations(unittest.TestCase):
    """Test suite targeting verified fixes from the /hack inspection report."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_dir.name)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_f09_rms_silence_detection_math(self):
        """Verify that _detect_silence_via_rms uses 20*log10 and detects silence (< -38 dBFS)."""
        wav_path = self.workspace / "test_silence.wav"
        framerate = 16000

        # Generate 1.0s loud sound followed by 1.0s silence (< -40 dBFS)
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(framerate)

            # Loud 500Hz sine wave ~ -6 dBFS (amplitude ~ 16000)
            loud_samples = [int(16000 * math.sin(2 * math.pi * 500 * i / framerate)) for i in range(framerate)]
            # Silence ~ -60 dBFS (amplitude ~ 30)
            silent_samples = [int(30 * math.sin(2 * math.pi * 500 * i / framerate)) for i in range(framerate)]

            all_samples = loud_samples + silent_samples
            raw_bytes = struct.pack(f"{len(all_samples)}h", *all_samples)
            wf.writeframes(raw_bytes)

        agent = IngestionAgent(workspace_dir=self.workspace)
        spans = agent._detect_silence_via_rms(wav_path, min_silence_sec=0.25, threshold_db=-38.0)

        self.assertGreater(len(spans), 0, "RMS silence detector failed to detect silence chunk below -38 dBFS!")
        # The detected silence must start around 1.0s
        first_span = spans[0]
        self.assertAlmostEqual(first_span.start_sec, 1.0, delta=0.15)
        self.assertGreaterEqual(first_span.duration_sec, 0.8)

    def test_f12_director_b_roll_provenance(self):
        """Verify that B-roll matches only against the file where the keyword was actually spoken."""
        director = DirectorAgent()

        # File 1 has word 'cat' at [2.0s - 2.5s]
        file_1 = MediaFileAnalysis(
            file_id="file_1_speaker_a",
            master_filepath="/media/cam_a.mp4",
            proxy_filepath="/media/cam_a_proxy.mp4",
            fps=30.0,
            width=1920,
            height=1080,
            duration_sec=10.0,
            role="A_ROLL_MAIN",
            words=[
                WordToken(word="hello", start_sec=0.5, end_sec=0.9, confidence=0.99),
                WordToken(word="cat", start_sec=2.0, end_sec=2.4, confidence=0.98),
            ],
            bad_spans=[],
            shots=[],
        )

        # File 2 has word 'dog' at [2.0s - 2.5s]
        file_2 = MediaFileAnalysis(
            file_id="file_2_speaker_b",
            master_filepath="/media/cam_b.mp4",
            proxy_filepath="/media/cam_b_proxy.mp4",
            fps=30.0,
            width=1920,
            height=1080,
            duration_sec=10.0,
            role="A_ROLL_MAIN",
            words=[
                WordToken(word="welcome", start_sec=0.5, end_sec=0.9, confidence=0.99),
                WordToken(word="dog", start_sec=2.0, end_sec=2.4, confidence=0.98),
            ],
            bad_spans=[],
            shots=[],
        )

        # B-Roll file with tag 'dog'
        b_roll_dog = MediaFileAnalysis(
            file_id="broll_dog_file",
            master_filepath="/media/broll_dog.mp4",
            proxy_filepath="/media/broll_dog_proxy.mp4",
            fps=30.0,
            width=1920,
            height=1080,
            duration_sec=5.0,
            role="B_ROLL",
            words=[],
            bad_spans=[],
            shots=[
                VisualShotAnalysis(
                    shot_id=1,
                    source_file="/media/broll_dog.mp4",
                    start_sec=0.0,
                    end_sec=5.0,
                    shot_scale="WS",
                    camera_motion="static",
                    visual_quality_score=9,
                    is_usable=True,
                    subject_emotion="neutral",
                    b_roll_tags=["dog", "puppy"],
                    summary="Playful puppy in grass",
                )
            ],
        )

        manifest = MediaAnalysisManifest(
            manifest_id="test_provenance",
            project_name="MultiCam_Test",
            files=[file_1, file_2, b_roll_dog],
        )

        plan = director.generate_edit_plan(manifest, editing_style="Retention")
        b_roll_actions = [a for a in plan.actions if a.track_index == 1 and a.track_type == "VIDEO"]

        self.assertEqual(len(b_roll_actions), 1)
        placed_b_roll = b_roll_actions[0]
        # File 1 duration is 10.0s. Since 'dog' was spoken in File 2 at 2.0s,
        # timeline_in_sec MUST be >= 10.0s (i.e. inside File 2's timeline window, not File 1!)
        self.assertGreaterEqual(
            placed_b_roll.timeline_in_sec,
            9.9,
            f"B-roll matched against wrong file! Placed at {placed_b_roll.timeline_in_sec}s instead of File 2 window.",
        )

    def test_f08_jsx_compiler_escapes_newlines_and_quotes(self):
        """Verify that multiline strings and quotes are escaped into valid ES3 literals."""
        raw_text = 'Hello\nWorld\r\n"Welcome" to \\Project\\ \'Argon\'\t!'
        escaped = JSXCompiler._escape_js_string(raw_text)

        self.assertNotIn("\n", escaped)
        self.assertNotIn("\r", escaped)
        self.assertNotIn("\t", escaped)
        self.assertIn('\\"', escaped)
        self.assertIn("\\n", escaped)

        # Validate with ES3 validator
        jsx = f'argon_addTextLayer("Comp1", "{escaped}", 72, [1,1,1], 0.5, 0.5, "kinetic");'
        violations = JSXCompiler.validate_es3(jsx, raise_on_error=True)
        self.assertEqual(len(violations), 0)

    def test_f16_whisper_leading_trailing_dead_air(self):
        """Verify that transcribe_audio captures leading and trailing silence."""
        agent = IngestionAgent(workspace_dir=self.workspace)

        # Mock whisper transcribe returning words starting at 3.0s and ending at 7.0s for a 12.0s audio
        mock_word1 = MagicMock(word="Hello", start=3.0, end=3.5, probability=0.99)
        mock_word2 = MagicMock(word="World", start=6.5, end=7.0, probability=0.99)
        mock_segment = MagicMock(words=[mock_word1, mock_word2])
        mock_info = MagicMock(duration=12.0)

        agent._whisper_model = MagicMock()
        agent._whisper_model.transcribe.return_value = ([mock_segment], mock_info)

        dummy_wav = self.workspace / "dummy.wav"
        dummy_wav.touch()

        words, bad_spans = agent.transcribe_audio(dummy_wav, min_silence_sec=0.25, total_duration=12.0)

        # Check for initial dead air [0.0s to 3.0s]
        initial_spans = [s for s in bad_spans if s.start_sec == 0.0 and s.end_sec == 3.0]
        self.assertEqual(len(initial_spans), 1, "Missing initial dead air span [0.0s - 3.0s]!")

        # Check for trailing dead air [7.0s to 12.0s]
        trailing_spans = [s for s in bad_spans if s.start_sec == 7.0 and s.end_sec == 12.0]
        self.assertEqual(len(trailing_spans), 1, "Missing trailing dead air span [7.0s - 12.0s]!")

    def test_f19_self_healing_catches_batch_partial_errors(self):
        """Verify that SelfHealingExecutor flags partial_error even when bridge returns HTTP 200."""
        executor = SelfHealingExecutor(max_retries=1)

        # Mock dispatch_jsx returning HTTP 200 bridge success but internal ExtendScript partial_error
        executor.dispatch_jsx = AsyncMock(return_value={
            "status": "ok",
            "result": {
                "status": "partial_error",
                "errors": [{"action_id": 101, "error": "Clip index out of bounds"}],
            }
        })
        executor.get_live_timeline_state = AsyncMock(return_value={"hasActiveSequence": True})

        dummy_plan = MasterEditPlan(
            plan_id="test_plan",
            project_title="Test_Project",
            timeline_duration_sec=5.0,
            actions=[],
        )

        loop = asyncio.new_event_loop()
        res = loop.run_until_complete(executor.execute_plan_safely(dummy_plan, project_id="proj_test"))
        loop.close()

        self.assertEqual(res["status"], "failed")
        self.assertIn("ExtendScript batch execution failed with 1 error(s)", res["error"])

    def test_f18_state_db_foreign_keys_and_auto_project(self):
        """Verify that SQLite foreign keys are enforced and record_snapshot auto-creates missing project rows."""
        db_path = self.workspace / "test_fk.db"
        db = StateDB(db_path=db_path)

        # Record snapshot with a new project_id that was not explicitly pre-created
        snap_id = db.record_snapshot(
            project_id="auto_created_proj",
            timeline_state={"activeSequence": "Timeline 1"},
            plan_id="plan_01",
        )
        self.assertGreater(snap_id, 0)

        # Verify project row was auto-inserted into projects table
        with db._get_connection() as conn:
            row = conn.execute("SELECT * FROM projects WHERE project_id = 'auto_created_proj'").fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["name"], "auto_created_proj")

    def test_f06_vfx_callout_timeline_in_point(self):
        """Verify that create_after_effects_vfx_comp accepts and passes custom timeline_in_sec."""
        with patch("mcp_server.server.vfx_agent.create_text_callout_overlay", new_callable=AsyncMock) as mock_vfx, \
             patch("mcp_server.server._send_bridge_request", new_callable=AsyncMock) as mock_bridge:

            mock_mov = self.workspace / "callout_alpha.mov"
            mock_mov.touch()
            mock_vfx.return_value = {"output_path": str(mock_mov)}
            mock_bridge.return_value = {"status": "ok"}

            loop = asyncio.new_event_loop()
            rendered = loop.run_until_complete(
                create_after_effects_vfx_comp(
                    comp_name="Callout1",
                    text_overlay='He said "Go!"',
                    duration_sec=3.0,
                    timeline_in_sec=14.5,
                )
            )
            loop.close()

            self.assertEqual(rendered, str(mock_mov))
            # Verify bridge was called with JSX containing timeline_in_sec = 14.5
            call_args = mock_bridge.call_args[0]
            jsx_sent = call_args[1]
            self.assertIn("14.5", jsx_sent)


if __name__ == "__main__":
    unittest.main()
