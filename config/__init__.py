"""Argon Video Engine Configuration Module."""

from .settings import (
    ArgonSettings,
    PREMIERE_TICKS_PER_SECOND,
    seconds_to_ticks,
    ticks_to_seconds,
    get_settings,
)

__all__ = [
    "ArgonSettings",
    "PREMIERE_TICKS_PER_SECOND",
    "seconds_to_ticks",
    "ticks_to_seconds",
    "get_settings",
]
