"""Test Hollywood Director Agent intelligent editing rules."""

import unittest
from agents.director_agent import DirectorAgent
from agents.schemas import (
    MediaFileAnalysis,
    MediaAnalysisManifest,
    SilenceOrFillerSpan,
    WordToken,
    VisualShotAnalysis,
)


class TestDirectorLogic(unittest.TestCase):
    def setUp(self):
        self.director = DirectorAgent()

    def test_calculate_speech_slices(self):
        # 10s clip with dead air between 3.0s and 4.0s
        bad_spans = [
            SilenceOrFillerSpan(start_sec=3.0, end_sec=4.0, duration_sec=1.0, kind="dead_air")
        ]
        slices = self.director._calculate_speech_slices(
            duration=10.0,
            bad_spans=bad_spans,
            max_silence=0.25,
            breath_padding=0.06,
        )
        self.assertEqual(len(slices), 2)
        # First slice starts at 0 and ends at 3.0 + 0.06 = 3.06
        self.assertEqual(slices[0][0], 0.0)
        self.assertEqual(slices[0][1], 3.06)
        # Second slice starts at 4.0 - 0.06 = 3.94 and ends at 10.0
        self.assertEqual(slices[1][0], 3.94)
        self.assertEqual(slices[1][1], 10.0)

    def test_short_filler_does_not_produce_overlapping_slices(self):
        # 0.10s filler word (less than 2 * 0.06s breath padding)
        bad_spans = [
            SilenceOrFillerSpan(start_sec=5.0, end_sec=5.10, duration_sec=0.10, kind="um_uh_filler")
        ]
        slices = self.director._calculate_speech_slices(
            duration=10.0,
            bad_spans=bad_spans,
            max_silence=0.25,
            breath_padding=0.06,
        )
        self.assertEqual(len(slices), 2)
        # End of first slice must be <= start of second slice (zero overlap)
        self.assertLessEqual(slices[0][1], slices[1][0])
        self.assertEqual(slices[0][0], 0.0)
        self.assertEqual(slices[0][1], 5.05)
        self.assertEqual(slices[1][0], 5.05)
        self.assertEqual(slices[1][1], 10.0)

    def test_dynamic_punch_in_alternation(self):
        # A-roll with two speech segments separated by pause
        a_roll = MediaFileAnalysis(
            file_id="a_roll_1",
            master_filepath="C:/footage/a_roll.mp4",
            proxy_filepath="C:/footage/proxies/a_roll.mp4",
            fps=30.0,
            width=1920,
            height=1080,
            duration_sec=10.0,
            role="A_ROLL_MAIN",
            words=[
                WordToken(word="First", start_sec=0.5, end_sec=1.0, confidence=0.9),
                WordToken(word="sentence", start_sec=1.1, end_sec=2.0, confidence=0.9),
                WordToken(word="Second", start_sec=5.0, end_sec=6.0, confidence=0.9),
                WordToken(word="sentence", start_sec=6.1, end_sec=7.0, confidence=0.9),
            ],
            bad_spans=[
                SilenceOrFillerSpan(start_sec=2.5, end_sec=4.5, duration_sec=2.0, kind="dead_air")
            ],
            shots=[
                VisualShotAnalysis(
                    shot_id=1,
                    source_file="C:/footage/a_roll.mp4",
                    start_sec=0.0,
                    end_sec=10.0,
                    shot_scale="MCU",
                    camera_motion="static",
                    visual_quality_score=9,
                    is_usable=True,
                    subject_emotion="neutral",
                    b_roll_tags=["host"],
                    summary="Host speaking",
                )
            ],
        )

        manifest = MediaAnalysisManifest(
            manifest_id="test_manifest",
            project_name="Test Project",
            files=[a_roll],
        )

        plan = self.director.generate_edit_plan(manifest, editing_style="Retention")
        video_actions = [a for a in plan.actions if a.track_type == "VIDEO" and a.track_index == 0]

        # Should have 2 video cuts
        self.assertEqual(len(video_actions), 2)
        # First cut scale = 100.0%
        self.assertEqual(video_actions[0].keyframes[0].scale, 100.0)
        # Second cut scale = 108.0% (punch-in)
        self.assertEqual(video_actions[1].keyframes[0].scale, 108.0)
        self.assertEqual(video_actions[1].keyframes[0].pos_y, 0.45)

    def test_semantic_b_roll_matching(self):
        a_roll = MediaFileAnalysis(
            file_id="a_roll",
            master_filepath="C:/footage/host.mp4",
            proxy_filepath="C:/footage/host_proxy.mp4",
            fps=30.0,
            width=1920,
            height=1080,
            duration_sec=6.0,
            role="A_ROLL_MAIN",
            words=[
                WordToken(word="look", start_sec=0.5, end_sec=0.8, confidence=0.9),
                WordToken(word="at", start_sec=0.9, end_sec=1.1, confidence=0.9),
                WordToken(word="this", start_sec=1.2, end_sec=1.4, confidence=0.9),
                WordToken(word="drone", start_sec=1.5, end_sec=2.0, confidence=0.9),
            ],
            bad_spans=[],
            shots=[],
        )

        b_roll = MediaFileAnalysis(
            file_id="b_roll_drone",
            master_filepath="C:/footage/drone.mp4",
            proxy_filepath="C:/footage/drone_proxy.mp4",
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
                    source_file="C:/footage/drone.mp4",
                    start_sec=0.0,
                    end_sec=5.0,
                    shot_scale="WS",
                    camera_motion="pan",
                    visual_quality_score=9,
                    is_usable=True,
                    subject_emotion="neutral",
                    b_roll_tags=["drone", "aerial", "landscape"],
                    summary="Aerial drone footage",
                )
            ],
        )

        manifest = MediaAnalysisManifest(
            manifest_id="test_manifest_broll",
            project_name="B-Roll Test",
            files=[a_roll, b_roll],
        )

        plan = self.director.generate_edit_plan(manifest, editing_style="Retention")
        v2_actions = [a for a in plan.actions if a.track_type == "VIDEO" and a.track_index == 1]

        # Should place B-roll on Track V2
        self.assertEqual(len(v2_actions), 1)
        self.assertEqual(v2_actions[0].master_filepath, "C:/footage/drone.mp4")
        self.assertIn("drone", v2_actions[0].reasoning.lower())


if __name__ == "__main__":
    unittest.main()
