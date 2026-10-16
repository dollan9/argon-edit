"""Test Self-Healing Execution Engine and Auto-Debugger."""

import unittest
from main_orchestrator import SelfHealingExecutor


class TestOrchestrator(unittest.TestCase):
    def setUp(self):
        self.executor = SelfHealingExecutor()

    def test_auto_debug_patches_forbidden_const_let(self):
        broken_jsx = "const path = 'test'; let count = 5;"
        error = "SyntaxError: Unexpected token const at line 1"
        patched = self.executor.auto_debug_patch(broken_jsx, error)
        self.assertNotIn("const", patched)
        self.assertNotIn("let", patched)
        self.assertIn("var path", patched)
        self.assertIn("var count", patched)

    def test_auto_debug_injects_ticks_constant_on_ticks_error(self):
        broken_jsx = "var timeInTicks = Math.round(sec * ARGON_TICKS_PER_SEC);"
        error = "ReferenceError: ARGON_TICKS_PER_SEC is undefined (ticks calculation)"
        patched = self.executor.auto_debug_patch(broken_jsx, error)
        self.assertIn("254016000000", patched)

    def test_auto_debug_injects_qe_enabler_on_qe_error(self):
        broken_jsx = "qe.project.getActiveSequence().addVideoTrack();"
        error = "ReferenceError: qe is undefined"
        patched = self.executor.auto_debug_patch(broken_jsx, error)
        self.assertIn("app.enableQE()", patched)


if __name__ == "__main__":
    unittest.main()
