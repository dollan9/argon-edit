# Long-Term Project Memory & Architectural Decisions (ADRs)

## ADR-001: Exact dBFS Logarithmic Formulation in Audio Ingestion
- **Context**: In `_detect_silence_via_rms`, energy threshold was compared against `20 * (rms / 32768.0 + 1e-9)` without `math.log10`.
- **Decision**: All dBFS conversions must use `20.0 * math.log10(max(ratio, 1e-9))`.
- **Impact**: Enables authentic dead-air cutting when running in offline/energy fallback mode without Whisper GPU acceleration.

## ADR-002: Word Token Provenance and Multi-Cam B-Roll Matching
- **Context**: When importing multiple A-roll takes, transcript timestamps from separate files could collide if evaluated only by time interval.
- **Decision**: `_match_b_roll` tracks `(source_file_id, WordToken)` pairs and enforces `act.source_file_id == file_id`.
- **Impact**: Multi-camera and episodic multi-file ingestion guarantees semantic B-roll placement exclusively on the corresponding camera angle.

## ADR-003: Double-Quoted ES3 String Literal Sanitization
- **Context**: ExtendScript ES3 parser terminates strings abruptly if unescaped quotes or raw newlines are present in text overlays.
- **Decision**: `JSXCompiler._escape_js_string` normalizes slashes to `/` and escapes `\r`, `\n`, `\t`, `"`, and `'`. All agents injecting text into JSX must route strings through this helper.
- **Impact**: Complete immunity to ExtendScript syntax parse failures on arbitrary user titles, subtitles, or lyrics.

## ADR-004: Adobe CEP Single-Threaded Queue Timeout Guard
- **Context**: ExtendScript engine in Premiere Pro can fail to trigger callbacks if modal dialogs appear or unhandled host errors freeze execution.
- **Decision**: `bridge_server.js` maintains a 45-second per-task timeout timer (`TASK_TIMEOUT_MS = 45000`) returning HTTP 504 and unlocking `isProcessingQueue` to protect the pipeline against permanent deadlocks.
- **Impact**: Ensures autonomous engine resilience and prevents server starvation.

## ADR-005: ExtendScript Batch Error Inspection in Orchestrator
- **Context**: `main_orchestrator.py` previously declared success based solely on the HTTP 200 response of the bridge.
- **Decision**: `SelfHealingExecutor.execute_plan_safely` inspects `result_payload` for `"status": "partial_error"` and non-empty `"errors"`, treating internal ExtendScript clip failures as execution retries.
- **Impact**: Guarantees self-healing retry and rollback loops engage whenever any clip operation fails on the timeline.
