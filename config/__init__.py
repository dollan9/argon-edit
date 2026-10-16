"""Argon Video Engine Configuration Module."""

from .settings import (
    ArgonSettings,
    PREMIERE_TICKS_PER_SECOND,
    EXACT_TIMEBASES,
    get_exact_fps,
    ticks_per_frame,
    frame_to_ticks,
    ticks_to_frame,
    seconds_to_frame_snapped_ticks,
    seconds_to_ticks,
    seconds_to_ticks_str,
    ticks_to_seconds,
    get_settings,
)

__all__ = [
    "ArgonSettings",
    "PREMIERE_TICKS_PER_SECOND",
    "EXACT_TIMEBASES",
    "get_exact_fps",
    "ticks_per_frame",
    "frame_to_ticks",
    "ticks_to_frame",
    "seconds_to_frame_snapped_ticks",
    "seconds_to_ticks",
    "seconds_to_ticks_str",
    "ticks_to_seconds",
    "get_settings",
]
