# Implementation Plan: Project Argon-Edit Hardening & Fixes

## Phase 0: Critical Correctness (P0)
- [ ] Task 0.1: Fix RMS dBFS formula in `agents/ingestion_agent.py` to use `20.0 * math.log10(...)`.
- [ ] Task 0.2: Add unit test in `tests/test_audio_agent.py` or new test file validating that `_detect_silence_via_rms` detects silence chunks under -38 dBFS.

## Phase 1: High-Priority Fixes (P1)
- [ ] Task 1.1: Fix B-roll matching in `agents/director_agent.py` by maintaining `file_id` provenance on spoken words.
- [ ] Task 1.2: Add newline, quote, and control character sanitization in `mcp_server/jsx_compiler.py` and escape callout texts in `agents/vfx_motion_agent.py` and `mcp_server/server.py`.
- [ ] Task 1.3: Add 45-second execution timeout guard per task in `adobe_cep_bridge/js/bridge_server.js` to prevent deadlocks.
- [ ] Task 1.4: Update `main_orchestrator.py` `SelfHealingExecutor` to inspect `result_payload` for `partial_error` and non-empty `errors`.
- [ ] Task 1.5: Fix `agents/ingestion_agent.py` `transcribe_audio` to capture leading silence (`w.start >= min_silence_sec`) and trailing silence (`duration - prev_end >= min_silence_sec`).

## Phase 2: Architecture & Integration Hardening (P2)
- [ ] Task 2.1: In `adobe_cep_bridge/jsx/premiere_core.jsx`, return error status if `volComponent` is not found on clip in `argon_applyAudioGainAndDucking`.
- [ ] Task 2.2: In `memory/state_db.py`, enable `PRAGMA foreign_keys = ON;` and ensure project ID references match.
- [ ] Task 2.3: In `mcp_server/server.py`, add configurable `timeline_in_sec` parameter to `create_after_effects_vfx_comp`.
- [ ] Task 2.4: In `adobe_cep_bridge/jsx/photoshop_core.jsx`, utilize passed `badgeColor` parameter.

## Phase 3: Comprehensive Regression Testing & Verification (Gate 1-5)
- [ ] Task 3.1: Write new regression test suite `tests/test_hack_fixes.py` verifying all 10 fixes.
- [ ] Task 3.2: Run full test suite (`python -m unittest discover tests`).
- [ ] Task 3.3: Run Hermes code review on git diff.
- [ ] Task 3.4: Complete `.agent/ultra/AUDIT.md` and present final Swedish milestone report.
