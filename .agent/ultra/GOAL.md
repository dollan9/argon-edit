# Project Goal & Requirements

## 1. Executive Objective
- **Primary Goal**: Implement production-hardening fixes for Project Argon-Edit based on verified /hack findings.
- **Target Audience / End Users**: Autonomous Video Production Pipeline & Adobe Creative Cloud Operators.
- **Complexity Tier**: Large (Multi-agent architecture across Python, ExtendScript ES3, Node.js CEP Bridge, and SQLite).

## 2. Intent Disambiguation
- **Explicit User Requirements**:
  - Remediate the defects uncovered in `/hack` inspection ("gå igenom / kör på").
  - Ensure zero regressions in existing 44 tests and add explicit regression coverage for fixed edge cases.
- **Agent Recommendations & Inferred Enhancements**:
  - P0 Fix: Correct RMS silence dBFS mathematical formula (`20.0 * math.log10(...)`).
  - P1 Fix: Scoped `source_file_id` provenance for B-roll keyword matching to prevent cross-file timestamp collisions.
  - P1 Fix: String sanitization and newline escaping in JSX generation to prevent syntax errors and code injection.
  - P1 Fix: 45s task execution timeout in Adobe CEP Bridge FIFO queue to prevent permanent deadlocks.
  - P1 Fix: Inspection of `partial_error` and `errors` array in Self-Healing Orchestrator.
  - P1 Fix: Initial and trailing silence detection in Whisper audio transcription.
  - P2 Fix: Error return in `argon_applyAudioGainAndDucking` when volume component is absent.
  - P3 Fix: Configurable `timeline_in_sec` for VFX callouts in FastMCP server.
  - P2 Fix: SQLite foreign key enforcement and project ID mapping.

## 3. Scope Boundaries
- **In-Scope**:
  - `agents/ingestion_agent.py`
  - `agents/director_agent.py`
  - `agents/vfx_motion_agent.py`
  - `mcp_server/jsx_compiler.py`
  - `mcp_server/server.py`
  - `adobe_cep_bridge/js/bridge_server.js`
  - `adobe_cep_bridge/jsx/premiere_core.jsx`
  - `main_orchestrator.py`
  - `memory/state_db.py`
  - `tests/` regression suite
- **Out-of-Scope**:
  - Rewriting existing working blueprints or changing external API endpoints.

## 4. Constraints & Guardrails
- **The ES3 ExtendScript Law**: Strictly ECMAScript 3 (1999) in all `.jsx` files.
- **The Premiere Ticks Law**: Exact constant `1s = 254016000000 Ticks` with frame-boundary snapping.
- **System Memory Safety**: RTX 3080 (10 GB VRAM) & 16 GB RAM buffers strictly maintained.
- **Hermes Code Review**: Mandatory independent code review on the final diff before completion.

## 5. Acceptance Criteria & Definition of Done (DoD)
- [ ] P0 math defect fixed: `_detect_silence_via_rms` detects silence correctly when RMS drops below threshold.
- [ ] P1 B-roll collision fixed: B-roll semantic matching respects `source_file_id`.
- [ ] P1 JSX sanitization: Special characters, quotes, and newlines in text overlays compile without syntax error.
- [ ] P1 CEP timeout: Task execution timeout implemented in `bridge_server.js`.
- [ ] P1 Self-Healing check: `partial_error` inside ExtendScript batch detected and triggers auto-debug/retry.
- [ ] P1 Initial/Trailing silence: Whisper transcription includes leading and trailing dead air.
- [ ] All 44 existing unit tests pass without regression.
- [ ] New regression tests pass for all fixed modules.
- [ ] Hermes review executed and findings verified.
