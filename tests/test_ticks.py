"""Test Premiere Ticks Law, fractional framerates, and frame snapping."""

import unittest
from fractions import Fraction
from config.settings import (
    PREMIERE_TICKS_PER_SECOND,
    get_exact_fps,
    ticks_per_frame,
    frame_to_ticks,
    ticks_to_frame,
    seconds_to_frame_snapped_ticks,
    seconds_to_ticks,
    seconds_to_ticks_str,
    ticks_to_seconds,
)


class TestPremiereTicks(unittest.TestCase):
    def test_ticks_constant(self):
        self.assertEqual(PREMIERE_TICKS_PER_SECOND, 254016000000)

    def test_one_second_conversion(self):
        ticks = seconds_to_ticks(1.0)
        self.assertEqual(ticks, 254016000000)
        self.assertEqual(seconds_to_ticks_str(1.0), "254016000000")
        self.assertAlmostEqual(ticks_to_seconds(ticks), 1.0, places=9)

    def test_fractional_seconds(self):
        # 0.5s
        half_sec_ticks = seconds_to_ticks(0.5)
        self.assertEqual(half_sec_ticks, 127008000000)
        self.assertAlmostEqual(ticks_to_seconds(half_sec_ticks), 0.5, places=9)

        # 0.04s (1 frame at 25fps)
        one_frame = seconds_to_ticks(0.04)
        self.assertEqual(one_frame, 10160640000)
        self.assertAlmostEqual(ticks_to_seconds(one_frame), 0.04, places=9)

    def test_zero_and_boundary(self):
        self.assertEqual(seconds_to_ticks(0.0), 0)
        self.assertEqual(seconds_to_ticks_str(0.0), "0")
        self.assertEqual(ticks_to_seconds(0), 0.0)

    def test_large_duration(self):
        # 2 hour timeline = 7200 seconds
        ticks = seconds_to_ticks(7200.0)
        self.assertEqual(ticks, 7200 * 254016000000)
        self.assertAlmostEqual(ticks_to_seconds(ticks), 7200.0, places=5)

    def test_exact_timebase_resolution(self):
        # 23.976 -> 24000/1001
        fps_23976 = get_exact_fps(23.976)
        self.assertEqual(fps_23976, Fraction(24000, 1001))

        # 29.97 -> 30000/1001
        fps_2997 = get_exact_fps(29.97)
        self.assertEqual(fps_2997, Fraction(30000, 1001))

        # 59.94 -> 60000/1001
        fps_5994 = get_exact_fps(59.94)
        self.assertEqual(fps_5994, Fraction(60000, 1001))

        # Integer timebases
        self.assertEqual(get_exact_fps(24), Fraction(24, 1))
        self.assertEqual(get_exact_fps(25.0), Fraction(25, 1))
        self.assertEqual(get_exact_fps(30.0), Fraction(30, 1))
        self.assertEqual(get_exact_fps(60.0), Fraction(60, 1))

    def test_frame_to_ticks_and_back_no_drift(self):
        # Test 10,000 frames at 23.976 fps
        fps = 23.976
        for frame in [0, 1, 24, 100, 1000, 86314]:
            ticks = frame_to_ticks(frame, fps)
            recovered_frame = ticks_to_frame(ticks, fps)
            self.assertEqual(recovered_frame, frame, f"Frame drift detected at frame {frame}")

    def test_frame_snapping_ticks(self):
        # At 24fps: 1 frame = 1/24 sec = 0.0416666... sec
        # A time of 0.041s should snap to frame 1 = 10584000000 ticks
        t1 = seconds_to_frame_snapped_ticks(0.041, fps=24)
        expected_t1 = frame_to_ticks(1, fps=24)
        self.assertEqual(t1, expected_t1)

        # At 23.976 fps: test frame snapping with seconds_to_ticks(sec, fps=23.976)
        snapped_ticks = seconds_to_ticks(1.0, fps=23.976)
        self.assertIsInstance(snapped_ticks, int)
        # 1.0 second at 23.976 fps snaps to frame 24
        self.assertEqual(ticks_to_frame(snapped_ticks, fps=23.976), 24)


if __name__ == "__main__":
    unittest.main()
