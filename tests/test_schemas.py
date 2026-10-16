"""Test Pydantic schemas validation and serialization."""

import unittest
from agents.schemas import (
    WordToken,
    SilenceOrFillerSpan,
    VisualShotAnalysis,
    MediaFileAnalysis,
    MediaAnalysisManifest,
    KeyframeTransform,
    TimelineClipAction,
    MasterEditPlan,
)


class TestSchemas(unittest.TestCase):
    def test_word_token(self):
        token = WordToken(word="hello", start_sec=1.5, end_sec=2.0, confidence=0.98)
        self.assertEqual(token.word, "hello")
        self.assertEqual(token.start_ticks, int(1.5 * 254016000000))
        self.assertEqual(token.end_ticks, int(2.0 * 254016000000))

    def test_silence_or_filler_span(self):
        span = SilenceOrFillerSpan(start_sec=2.0, end_sec=2.8, duration_sec=0.8, kind="dead_air")
        self.assertEqual(span.kind, "dead_air")
        self.assertEqual(span.duration_sec, 0.8)

    def test_visual_shot_analysis(self):
        shot = VisualShotAnalysis(
            shot_id=1,
            source_file="C:/test.mp4",
            start_sec=0.0,
            end_sec=4.5,
            shot_scale="MCU",
            camera_motion="static",
            visual_quality_score=9,
            is_usable=True,
            subject_emotion="confident",
            b_roll_tags=["host", "studio"],
            summary="Host speaking directly to camera",
        )
        self.assertEqual(shot.shot_scale, "MCU")
        self.assertEqual(shot.visual_quality_score, 9)

    def test_timeline_clip_action_and_master_plan(self):
        action = TimelineClipAction(
            action_id=1,
            track_type="VIDEO",
            track_index=0,
            source_file_id="clip_01",
            master_filepath="C:/footage/a_roll.mp4",
            src_in_sec=1.0,
            src_out_sec=5.0,
            timeline_in_sec=0.0,
            keyframes=[KeyframeTransform(time_offset_sec=0.0, scale=108.0)],
            reasoning="Dialogue slice with 108% punch-in",
        )
        self.assertEqual(action.timeline_in_ticks_str, "0")
        self.assertEqual(action.src_in_ticks_str, str(254016000000))

        plan = MasterEditPlan(
            plan_id="plan_test_01",
            project_title="Test Project",
            timeline_duration_sec=4.0,
            actions=[action],
        )
        json_str = plan.model_dump_json()
        self.assertIn("plan_test_01", json_str)
        deserialized = MasterEditPlan.model_validate_json(json_str)
        self.assertEqual(len(deserialized.actions), 1)
        self.assertEqual(deserialized.actions[0].keyframes[0].scale, 108.0)


if __name__ == "__main__":
    unittest.main()
