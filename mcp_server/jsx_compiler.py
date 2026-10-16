"""JSX Compiler and ES3 Syntax Validator for Project Argon.

Enforces:
1. THE ES3 EXTENDSCRIPT LAW: Strictly ECMAScript 3 (1999) output.
   Flags or rejects const, let, arrow functions, template literals, and non-polyfilled methods.
2. THE PREMIERE TICKS LAW: 1 Second = 254016000000 Ticks.
"""

from __future__ import annotations
import re
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

from config.settings import seconds_to_ticks_str, PREMIERE_TICKS_PER_SECOND
from agents.schemas import MasterEditPlan, TimelineClipAction

logger = logging.getLogger("argon.mcp.compiler")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class ES3ValidationError(ValueError):
    """Raised when generated ExtendScript contains illegal ECMAScript 6+ tokens."""
    pass


class JSXCompiler:
    """Compiles and validates Python parameters into safe ES3 ExtendScript snippets."""

    FORBIDDEN_ES6_PATTERNS = [
        (r"\bconst\s+", "const declaration (use var)"),
        (r"\blet\s+", "let declaration (use var)"),
        (r"=>", "arrow function (use function() {})"),
        (r"`[^`]*`", "template literal string (use concatenation)"),
        (r"\.map\(", "Array.map (use standard for loop)"),
        (r"\.filter\(", "Array.filter (use standard for loop)"),
        (r"\.forEach\(", "Array.forEach (use standard for loop)"),
    ]

    @classmethod
    def validate_es3(cls, jsx_code: str, raise_on_error: bool = True) -> List[str]:
        """Verify that JSX code is 100% compliant with Adobe ExtendScript ES3 engine."""
        violations = []
        for pattern, reason in cls.FORBIDDEN_ES6_PATTERNS:
            matches = list(re.finditer(pattern, jsx_code))
            if matches:
                violations.append(f"Found {len(matches)} instance(s) of {reason}")

        if violations and raise_on_error:
            raise ES3ValidationError(f"ES3 Compliance Failure: {'; '.join(violations)}")
        return violations

    @staticmethod
    def _escape_js_string(s: str) -> str:
        """Escape string for safe insertion into JavaScript double-quoted literal."""
        norm = str(s).replace("\\", "/")
        norm = norm.replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
        return norm.replace('"', '\\"').replace("'", "\\'")

    @classmethod
    def compile_init_project(
        cls,
        project_path: str = "",
        sequence_name: str = "Argon_Master_Timeline",
        fps: float = 30.0,
        width: int = 1920,
        height: int = 1080,
    ) -> str:
        code = (
            f'argon_initProject("{cls._escape_js_string(project_path)}", '
            f'"{cls._escape_js_string(sequence_name)}", {fps}, {width}, {height});'
        )
        cls.validate_es3(code)
        return code

    @classmethod
    def compile_import_files(cls, file_paths: List[str]) -> str:
        clean_paths = [cls._escape_js_string(p) for p in file_paths]
        json_array = json.dumps(clean_paths)
        code = f"argon_importFiles({json_array});"
        cls.validate_es3(code)
        return code

    @classmethod
    def compile_insert_clip(
        cls,
        file_path: str,
        src_in_sec: float,
        src_out_sec: float,
        timeline_in_sec: float,
        v_track_idx: int = 0,
        a_track_idx: int = -1,
    ) -> str:
        escaped = cls._escape_js_string(file_path)
        code = (
            f'argon_insertClip("{escaped}", {float(src_in_sec)}, {float(src_out_sec)}, '
            f'{float(timeline_in_sec)}, {int(v_track_idx)}, {int(a_track_idx)});'
        )
        cls.validate_es3(code)
        return code

    @classmethod
    def compile_apply_transform(
        cls,
        v_track_idx: int,
        clip_idx: int,
        scale_val: float,
        pos_x: float = 0.5,
        pos_y: float = 0.5,
    ) -> str:
        code = (
            f"argon_applyTransform({int(v_track_idx)}, {int(clip_idx)}, "
            f"{float(scale_val)}, {float(pos_x)}, {float(pos_y)});"
        )
        cls.validate_es3(code)
        return code

    @classmethod
    def compile_apply_audio_gain_and_ducking(
        cls, a_track_idx: int, clip_idx: int, target_db: float
    ) -> str:
        code = f"argon_applyAudioGainAndDucking({int(a_track_idx)}, {int(clip_idx)}, {float(target_db)});"
        cls.validate_es3(code)
        return code

    @classmethod
    def compile_apply_lumetri_lut(
        cls, v_track_idx: int, clip_idx: int, lut_path: str
    ) -> str:
        escaped = cls._escape_js_string(lut_path)
        code = f'argon_applyLumetriLUT({int(v_track_idx)}, {int(clip_idx)}, "{escaped}");'
        cls.validate_es3(code)
        return code

    @classmethod
    def compile_get_timeline_state(cls) -> str:
        code = "argon_getTimelineStateJSON();"
        cls.validate_es3(code)
        return code

    @classmethod
    def compile_export_via_ame(cls, output_path: str, preset_path: str = "") -> str:
        out_esc = cls._escape_js_string(output_path)
        preset_esc = cls._escape_js_string(preset_path)
        code = f'argon_exportViaAME("{out_esc}", "{preset_esc}");'
        cls.validate_es3(code)
        return code

    @classmethod
    def compile_edit_plan_batch(cls, plan: MasterEditPlan) -> str:
        """Compile complete MasterEditPlan into a single transactional ES3 ExtendScript block."""
        lines = [
            "(function() {",
            "    var results = [];",
            "    var errors = [];",
            "    var startTime = new Date().getTime();",
            "    if (app.enableQE) { app.enableQE(); }",
            "",
        ]

        # 1. Pre-import all unique media files
        unique_paths = list({a.master_filepath for a in plan.actions})
        clean_paths = [cls._escape_js_string(p) for p in unique_paths]
        lines.append(f"    var importRes = argon_importFiles({json.dumps(clean_paths)});")
        lines.append("    results.push({ action: 'importFiles', result: importRes });")
        lines.append("")

        # Track placed clip counts per track for correct index resolution
        v_track_clip_counts: Dict[int, int] = {}
        a_track_clip_counts: Dict[int, int] = {}

        # 2. Sequential clip inserts and transform applications
        for idx, act in enumerate(plan.actions):
            t_in = float(act.timeline_in_sec)
            s_in = float(act.src_in_sec)
            s_out = float(act.src_out_sec)
            is_video = (act.track_type == "VIDEO")
            v_idx = act.track_index if is_video else -1
            a_idx = act.track_index if not is_video else -1
            esc_path = cls._escape_js_string(act.master_filepath)

            lines.append(f"    // Action {act.action_id} ({act.track_type} Track {act.track_index})")
            lines.append("    try {")
            lines.append(
                f'        var r{idx} = argon_insertClip("{esc_path}", {s_in}, {s_out}, {t_in}, {v_idx}, {a_idx});'
            )
            lines.append(f"        results.push({{ action_id: {act.action_id}, res: r{idx} }});")

            if is_video and v_idx >= 0:
                clip_c = v_track_clip_counts.get(v_idx, 0)
                v_track_clip_counts[v_idx] = clip_c + 1

                lines.append(f"        var pr{idx} = (typeof JSON !== 'undefined' && JSON.parse) ? JSON.parse(r{idx}) : null;")
                lines.append(f"        var cIdx{idx} = (pr{idx} && typeof pr{idx}.clipIndex !== 'undefined' && pr{idx}.clipIndex >= 0) ? pr{idx}.clipIndex : {clip_c};")

                # Apply keyframe transforms (punch-ins)
                for kf in act.keyframes:
                    if kf.scale != 100.0 or kf.pos_x != 0.5 or kf.pos_y != 0.5:
                        lines.append(
                            f"        argon_applyTransform({v_idx}, cIdx{idx}, {kf.scale}, {kf.pos_x}, {kf.pos_y});"
                        )

                # Apply LUT if specified
                if act.lumetri_lut_path:
                    lut_esc = cls._escape_js_string(act.lumetri_lut_path)
                    lines.append(f'        argon_applyLumetriLUT({v_idx}, cIdx{idx}, "{lut_esc}");')

            elif not is_video and a_idx >= 0:
                clip_c = a_track_clip_counts.get(a_idx, 0)
                a_track_clip_counts[a_idx] = clip_c + 1

            lines.append("    } catch (actErr) {")
            lines.append(
                f"        errors.push({{ action_id: {act.action_id}, error: actErr.message || String(actErr) }});"
            )
            lines.append("    }")
            lines.append("")

        lines.extend([
            "    var timelineState = argon_getTimelineStateJSON();",
            "    return JSON.stringify({",
            "        status: errors.length === 0 ? 'ok' : 'partial_error',",
            "        totalActions: " + str(len(plan.actions)) + ",",
            "        executionMs: (new Date().getTime() - startTime),",
            "        results: results,",
            "        errors: errors,",
            "        postTimelineState: timelineState",
            "    });",
            "})();",
        ])

        batch_code = "\n".join(lines)
        cls.validate_es3(batch_code)
        return batch_code
