"""Vision Agent for Project Argon Video Engine.

Uses meta/llama-3.2-90b-vision-instruct via Nvidia NIM API to analyze
extracted keyframes from 480p proxies, classifying shot scale, camera motion,
quality, emotion, and B-roll descriptive tags.
"""

from __future__ import annotations
import os
import base64
import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any

from agents.base_agent import BaseNvidiaAgent
from agents.schemas import VisualShotAnalysis, MediaFileAnalysis
from config.settings import get_settings

logger = logging.getLogger("argon.agents.vision")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class VisionAgent:
    """Extracts keyframes from low-res proxies and runs batched multimodal vision evaluation."""

    def __init__(self, agent: Optional[BaseNvidiaAgent] = None):
        settings = get_settings()
        self.agent = agent or BaseNvidiaAgent(
            default_model=settings.vision_model,
            fallback_model=settings.director_fallback_model,
        )
        self.keyframes_dir = settings.workspace_dir / "keyframes"
        self.keyframes_dir.mkdir(parents=True, exist_ok=True)

    def extract_keyframe(self, proxy_path: Path, timestamp_sec: float) -> Path:
        """Extract a single JPEG keyframe from proxy at specified timestamp."""
        stem = proxy_path.stem
        out_jpg = self.keyframes_dir / f"{stem}_frame_{int(timestamp_sec * 1000)}ms.jpg"
        if out_jpg.exists():
            return out_jpg

        cmd = [
            "ffmpeg",
            "-y",
            "-ss", str(max(0.0, timestamp_sec)),
            "-i", str(proxy_path),
            "-frames:v", "1",
            "-q:v", "3",
            str(out_jpg),
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return out_jpg

    def _encode_image(self, image_path: Path) -> str:
        """Read image and encode to base64 string."""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    async def analyze_shot(
        self,
        proxy_path: Path,
        shot_id: int,
        source_file: str,
        start_sec: float,
        end_sec: float,
    ) -> VisualShotAnalysis:
        """Analyze a shot segment by evaluating mid-point keyframe with Llama-3.2-90B-Vision."""
        mid_point = (start_sec + end_sec) / 2.0
        frame_path = self.extract_keyframe(proxy_path, mid_point)

        # If Nvidia API key is not configured, return deterministic baseline analysis
        if not self.agent.api_key:
            logger.info("Nvidia API key not set, using heuristic visual classification.")
            return VisualShotAnalysis(
                shot_id=shot_id,
                source_file=source_file,
                start_sec=round(start_sec, 3),
                end_sec=round(end_sec, 3),
                shot_scale="MCU",
                camera_motion="static",
                visual_quality_score=8,
                is_usable=True,
                subject_emotion="neutral",
                b_roll_tags=["talking_head", Path(source_file).stem.lower()],
                summary=f"Shot {shot_id} [{start_sec}s - {end_sec}s]: talking head subject in frame.",
            )

        base64_img = self._encode_image(frame_path)
        system_prompt = (
            "You are an expert video director and cinematography analysis system. "
            "Analyze this video frame and return ONLY a valid JSON object matching this schema:\n"
            "{\n"
            '  "shot_scale": "ECU" | "CU" | "MCU" | "MS" | "WS" | "EWS" | "SCREEN_CAPTURE",\n'
            '  "camera_motion": "static" | "pan" | "tilt" | "zoom_in" | "zoom_out" | "handheld_shake",\n'
            '  "visual_quality_score": 1-10 (integer),\n'
            '  "is_usable": true | false,\n'
            '  "subject_emotion": "confident" | "excited" | "serious" | "neutral" | "smiling",\n'
            '  "b_roll_tags": ["tag1", "tag2"],\n'
            '  "summary": "one sentence description of what is visible"\n'
            "}"
        )

        user_content = [
            {"type": "text", "text": "Analyze this shot keyframe according to cinematography standards:"},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"},
            },
        ]

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        try:
            settings = get_settings()
            data = await self.agent.chat_completion_json(
                messages=messages,
                model=settings.vision_model,
                temperature=0.1,
            )
            return VisualShotAnalysis(
                shot_id=shot_id,
                source_file=source_file,
                start_sec=round(start_sec, 3),
                end_sec=round(end_sec, 3),
                shot_scale=data.get("shot_scale", "MCU"),
                camera_motion=data.get("camera_motion", "static"),
                visual_quality_score=int(data.get("visual_quality_score", 8)),
                is_usable=bool(data.get("is_usable", True)),
                subject_emotion=data.get("subject_emotion", "neutral"),
                b_roll_tags=data.get("b_roll_tags", [Path(source_file).stem.lower()]),
                summary=data.get("summary", f"Shot {shot_id} analysis"),
            )
        except Exception as e:
            logger.warning(f"Vision API call failed for shot {shot_id}: {e}. Using fallback classification.")
            return VisualShotAnalysis(
                shot_id=shot_id,
                source_file=source_file,
                start_sec=round(start_sec, 3),
                end_sec=round(end_sec, 3),
                shot_scale="MCU",
                camera_motion="static",
                visual_quality_score=7,
                is_usable=True,
                subject_emotion="neutral",
                b_roll_tags=[Path(source_file).stem.lower()],
                summary=f"Heuristic fallback for shot {shot_id}",
            )

    async def enrich_media_analysis(
        self, file_analysis: MediaFileAnalysis, batch_size: int = 3
    ) -> MediaFileAnalysis:
        """Batch process and enrich all detected shots in a MediaFileAnalysis object."""
        proxy_path = Path(file_analysis.proxy_filepath)
        enriched_shots: List[VisualShotAnalysis] = []

        # Batch to respect GPU memory & API rate limits
        for i in range(0, len(file_analysis.shots), batch_size):
            batch = file_analysis.shots[i:i + batch_size]
            for shot in batch:
                enriched = await self.analyze_shot(
                    proxy_path=proxy_path,
                    shot_id=shot.shot_id,
                    source_file=file_analysis.master_filepath,
                    start_sec=shot.start_sec,
                    end_sec=shot.end_sec,
                )
                enriched_shots.append(enriched)

        file_analysis.shots = enriched_shots
        return file_analysis
