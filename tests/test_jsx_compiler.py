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
        self.assertIn("argon_insertClip", batch)
        self.assertIn("argon_applyTransform(0, 0, 108.0", batch)
        # Verify strict ES3 compliance of the whole generated batch
        self.assertEqual(len(JSXCompiler.validate_es3(batch, raise_on_error=False)), 0)


if __name__ == "__main__":
    unittest.main()
