"""Audio Master Agent for Project Argon.

Enforces broadcast audio standards:
1. -14.0 LUFS integrated loudness normalization.
2. Dynamic audio ducking envelopes (A1 dialogue ducks A3 music to -22 dB).
3. Strategic SFX placement (whooshes, risers, impacts) on Track A2 at scene cuts.
4. J-cut (-0.25s audio lead) and L-cut (+0.25s audio tail) boundary calculations.
"""

from __future__ import annotations
import math
import logging
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

from config.settings import get_settings
from agents.schemas import MasterEditPlan, TimelineClipAction

logger = logging.getLogger("argon.agents.audio")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class AudioMasterAgent:
    """Calculates ducking envelopes, loudness targets, SFX alignment, and J/L cut audio offsets."""

    def __init__(self, target_lufs: Optional[float] = None):
        settings = get_settings()
        self.target_lufs = target_lufs or settings.audio_lufs_target
        self.workspace_dir = settings.workspace_dir

    def calculate_ducking_envelope(
        self,
        dialogue_actions: List[TimelineClipAction],
        ducked_db: float = -22.0,
        regular_db: float = -10.0,
        ramp_sec: float = 0.20,
    ) -> List[Dict[str, Any]]:
        """Calculate keyframe envelope for background music on Track A3."""
        envelope: List[Dict[str, Any]] = []
        if not dialogue_actions:
            return envelope

        # Sort dialogue clips by timeline in
        sorted_dialogue = sorted(dialogue_actions, key=lambda a: a.timeline_in_sec)

        for clip in sorted_dialogue:
            dur = clip.src_out_sec - clip.src_in_sec
            t_start = clip.timeline_in_sec
            t_end = t_start + dur

            # Duck down when speech starts
            envelope.append({
                "time_sec": max(0.0, t_start - ramp_sec),
                "gain_db": regular_db,
                "type": "duck_pre",
            })
            envelope.append({
                "time_sec": t_start,
                "gain_db": ducked_db,
                "type": "duck_active",
            })
            # Duck back up after speech concludes
            envelope.append({
                "time_sec": t_end,
                "gain_db": ducked_db,
                "type": "unduck_active",
            })
            envelope.append({
                "time_sec": t_end + ramp_sec,
                "gain_db": regular_db,
                "type": "unduck_post",
            })

        return envelope

    def apply_jl_cut_offsets(
        self, plan: MasterEditPlan, offset_sec: float = 0.25
    ) -> MasterEditPlan:
        """Enforce J-cuts (audio starts before video) or L-cuts on scene transitions and B-roll cutaways."""
        v_clips = [a for a in plan.actions if a.track_type == "VIDEO"]
        a_clips = [a for a in plan.actions if a.track_type == "AUDIO"]

        for idx in range(1, len(v_clips)):
            prev_v = v_clips[idx - 1]
            curr_v = v_clips[idx]

            # Scene transition or A-roll to B-roll cutaway
            is_scene_transition = (curr_v.source_file_id != prev_v.source_file_id)
            is_b_roll_transition = (curr_v.track_index != prev_v.track_index)

            if is_scene_transition or is_b_roll_transition:
                # Find matching dialogue audio action for curr_v
                for a_act in a_clips:
                    if (
                        a_act.source_file_id == curr_v.source_file_id
                        and abs(a_act.src_in_sec - curr_v.src_in_sec) < 0.05
                    ):
                        # Apply J-cut: dialogue starts offset_sec earlier
                        if a_act.src_in_sec >= offset_sec and a_act.timeline_in_sec >= offset_sec:
                            a_act.src_in_sec = round(a_act.src_in_sec - offset_sec, 3)
                            a_act.timeline_in_sec = round(a_act.timeline_in_sec - offset_sec, 3)
                            a_act.j_l_cut_audio_offset_sec = -offset_sec
                            a_act.reasoning += f" Applied J-cut audio lead of -{offset_sec}s."
                            curr_v.j_l_cut_audio_offset_sec = -offset_sec
                        break
                if is_b_roll_transition and curr_v.track_index == 1 and curr_v.j_l_cut_audio_offset_sec == 0.0:
                    curr_v.j_l_cut_audio_offset_sec = -offset_sec

        return plan

    def place_transition_sfx(
        self,
        plan: MasterEditPlan,
        sfx_library_paths: List[str],
    ) -> MasterEditPlan:
        """Place accent sound effects (whooshes, risers) on Track A2 at visual cuts."""
        if not sfx_library_paths:
            return plan

        v_cuts = [a for a in plan.actions if a.track_type == "VIDEO" and a.track_index in (0, 1)]
        sfx_actions: List[TimelineClipAction] = []
        sfx_id_base = 50000

        for i, cut in enumerate(v_cuts):
            # Place whoosh transition at punch-in cuts or B-roll entries
            has_punch = any(k.scale > 102.0 for k in cut.keyframes)
            is_b_roll = (cut.track_index == 1)

            if (has_punch or is_b_roll) and cut.timeline_in_sec > 0.5:
                sfx_file = sfx_library_paths[i % len(sfx_library_paths)]
                sfx_actions.append(
                    TimelineClipAction(
                        action_id=sfx_id_base + i,
                        track_type="AUDIO",
                        track_index=1,  # A2 (SFX)
                        source_file_id=f"sfx_{Path(sfx_file).stem}",
                        master_filepath=sfx_file,
                        src_in_sec=0.0,
                        src_out_sec=1.2,
                        timeline_in_sec=round(cut.timeline_in_sec - 0.15, 3),  # Lead transition slightly
                        j_l_cut_audio_offset_sec=0.0,
                        reasoning=f"Accent SFX placed at {'punch-in cut' if has_punch else 'B-roll cutaway'}.",
                    )
                )

        plan.actions.extend(sfx_actions)
        plan.actions.sort(key=lambda a: (a.timeline_in_sec, a.track_index))
        return plan

    def normalize_loudness_ffmpeg(
        self, input_wav: Path, output_wav: Path, target_lufs: Optional[float] = None
    ) -> Path:
        """Apply EBU R128 loudness normalization via ffmpeg loudnorm filter."""
        lufs = target_lufs or self.target_lufs
        output_wav.parent.mkdir(parents=True, exist_ok=True)

        cmd = [
            "ffmpeg",
            "-y",
            "-i", str(input_wav),
            "-af", f"loudnorm=I={lufs}:TP=-1.5:LRA=11",
            "-ar", "48000",
            str(output_wav),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return output_wav
