"""Test JSX Compiler and strict ES3 validation."""

import unittest
from mcp_server.jsx_compiler import JSXCompiler, ES3ValidationError
from agents.schemas import MasterEditPlan, TimelineClipAction, KeyframeTransform


class TestJSXCompiler(unittest.TestCase):
    def test_es3_validation_pass(self):
        valid_es3 = """
        var x = 10;
        function test(a, b) {
            var sum = 0;
            for (var i = 0; i < 5; i++) {
                sum = sum + i;
            }
            return sum;
        }
        """
        violations = JSXCompiler.validate_es3(valid_es3, raise_on_error=False)
        self.assertEqual(len(violations), 0)

    def test_es3_validation_catches_const(self):
        code = "const a = 10;"
        with self.assertRaises(ES3ValidationError):
            JSXCompiler.validate_es3(code, raise_on_error=True)

    def test_es3_validation_catches_let(self):
        code = "let b = 20;"
        with self.assertRaises(ES3ValidationError):
            JSXCompiler.validate_es3(code, raise_on_error=True)

    def test_es3_validation_catches_arrow(self):
        code = "var fn = () => 42;"
        with self.assertRaises(ES3ValidationError):
            JSXCompiler.validate_es3(code, raise_on_error=True)

    def test_es3_validation_catches_template_literals(self):
        code = "var s = `hello ${name}`;"
        with self.assertRaises(ES3ValidationError):
            JSXCompiler.validate_es3(code, raise_on_error=True)

    def test_compile_insert_clip(self):
        jsx = JSXCompiler.compile_insert_clip("C:/media/video.mp4", 1.5, 4.5, 0.0, 0, 0)
        self.assertIn("argon_insertClip", jsx)
        self.assertIn("C:/media/video.mp4", jsx)
        self.assertIn("1.5", jsx)
        self.assertIn("4.5", jsx)

    def test_compile_edit_plan_batch(self):
        action1 = TimelineClipAction(
            action_id=1,
            track_type="VIDEO",
            track_index=0,
            source_file_id="clip_01",
            master_filepath="C:/footage/a_roll.mp4",
            src_in_sec=0.0,
            src_out_sec=3.0,
            timeline_in_sec=0.0,
            keyframes=[KeyframeTransform(time_offset_sec=0.0, scale=100.0)],
            reasoning="Wide shot",
        )
        action2 = TimelineClipAction(
            action_id=2,
            track_type="VIDEO",
            track_index=0,
            source_file_id="clip_01",
            master_filepath="C:/footage/a_roll.mp4",
            src_in_sec=3.5,
            src_out_sec=6.5,
            timeline_in_sec=3.0,
            keyframes=[KeyframeTransform(time_offset_sec=0.0, scale=108.0)],
            reasoning="Punch-in cut",
        )

        plan = MasterEditPlan(
            plan_id="test_plan",
            project_title="Test",
            timeline_duration_sec=6.0,
            actions=[action1, action2],
        )

        batch = JSXCompiler.compile_edit_plan_batch(plan)
        self.assertIn("argon_importFiles", batch)
        self.assertIn("argon_applyTransform(0,", batch)
        self.assertIn("108.0", batch)
        # Verify that clip index for action 2 defaults to 1 (second clip), not 0
        self.assertIn("cIdx1", batch)
        # Verify strict ES3 compliance of the whole generated batch
        self.assertEqual(len(JSXCompiler.validate_es3(batch, raise_on_error=False)), 0)

    def test_compile_video_and_audio_separate_tracks(self):
        video_act = TimelineClipAction(
            action_id=1,
            track_type="VIDEO",
            track_index=0,
            source_file_id="clip_01",
            master_filepath="C:/footage/a_roll.mp4",
            src_in_sec=0.0,
            src_out_sec=3.0,
            timeline_in_sec=0.0,
            reasoning="V1 dialogue",
        )
        audio_act = TimelineClipAction(
            action_id=2,
            track_type="AUDIO",
            track_index=2,  # A3 (Music)
            source_file_id="music_01",
            master_filepath="C:/music/bg.mp3",
            src_in_sec=0.0,
            src_out_sec=10.0,
            timeline_in_sec=0.0,
            reasoning="A3 background music",
        )
        plan = MasterEditPlan(
            plan_id="track_test",
            project_title="Track Test",
            timeline_duration_sec=10.0,
            actions=[video_act, audio_act],
        )
        batch = JSXCompiler.compile_edit_plan_batch(plan)

        # Video action must have v_idx=0 and a_idx=-1
        self.assertIn('argon_insertClip("C:/footage/a_roll.mp4", 0.0, 3.0, 0.0, 0, -1)', batch)
        # Audio action must have v_idx=-1 and a_idx=2 (not overwriting V1!)
        self.assertIn('argon_insertClip("C:/music/bg.mp3", 0.0, 10.0, 0.0, -1, 2)', batch)
        self.assertEqual(len(JSXCompiler.validate_es3(batch, raise_on_error=False)), 0)

    def test_es3_validation_ignores_strings_and_comments(self):
        """Verify that words like 'const' or 'let' inside strings or comments do not trigger false positives."""
        valid_code_with_keywords_in_literals = '''
        // const old_unused_var = 1;
        /* let me explain how this works */
        var title = "The constant gardener";
        var subtitle = 'let it be';
        var desc = "Values like => or .map() in dialogue: let us go";
        '''
        violations = JSXCompiler.validate_es3(valid_code_with_keywords_in_literals, raise_on_error=True)
        self.assertEqual(len(violations), 0)


if __name__ == "__main__":
    unittest.main()

