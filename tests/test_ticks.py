"""Test Premiere Ticks Law and conversion precision."""

import unittest
from config.settings import (
    PREMIERE_TICKS_PER_SECOND,
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


if __name__ == "__main__":
    unittest.main()
