"""Ingestion Agent for Project Argon Video Engine.

Enforces THE PROXY ANALYSIS LAW:
1. Extracts 16kHz mono .wav for audio transcription & RMS analysis.
2. Extracts 480p low-bitrate proxy .mp4 for scene detection and vision.
3. Maps all timeline timecodes and decisions back to high-res master files.
4. Uses faster-whisper with word timestamps and VAD filtering.
"""

from __future__ import annotations
import os
import re
import math
import json
import wave
import struct
import shutil
import logging
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple, Literal

from config.settings import get_settings
from agents.schemas import (
    WordToken,
    SilenceOrFillerSpan,
    VisualShotAnalysis,
    MediaFileAnalysis,
)

logger = logging.getLogger("argon.agents.ingestion")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

FILLER_WORDS = {
    "um", "uh", "er", "ah", "like", "you know", "sort of", "kind of", "so basically", "umm", "uhh"
}


class IngestionAgent:
    """Manages proxy generation, transcription, scene detection, and audio analysis."""

    def __init__(self, workspace_dir: Optional[Path] = None):
        settings = get_settings()
        self.workspace_dir = workspace_dir or settings.workspace_dir
        self.proxies_dir = self.workspace_dir / "proxies"
        self.audio_dir = self.workspace_dir / "audio_16k"
        self.proxies_dir.mkdir(parents=True, exist_ok=True)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        self._whisper_model = None

    def _get_ffmpeg_cmd(self) -> str:
        """Locate ffmpeg binary."""
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise FileNotFoundError("ffmpeg executable not found in PATH.")
        return ffmpeg

    def _get_ffprobe_cmd(self) -> str:
        """Locate ffprobe binary."""
        ffprobe = shutil.which("ffprobe")
        if not ffprobe:
            raise FileNotFoundError("ffprobe executable not found in PATH.")
        return ffprobe

    def probe_media_file(self, file_path: Path) -> dict:
        """Probe media file for duration, resolution, and fps."""
        ffprobe = self._get_ffprobe_cmd()
        cmd = [
            ffprobe,
            "-v", "error",
            "-show_entries", "stream=width,height,r_frame_rate,duration,codec_type",
            "-show_entries", "format=duration",
            "-of", "json",
            str(file_path),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)

        width = 1920
        height = 1080
        fps = 30.0
        duration = 0.0

        if "format" in data and "duration" in data["format"]:
            try:
                duration = float(data["format"]["duration"])
            except (ValueError, TypeError):
                duration = 0.0

        streams = data.get("streams", [])
        for s in streams:
            if s.get("codec_type") == "video":
                width = int(s.get("width", 1920))
                height = int(s.get("height", 1080))
                r_fps = s.get("r_frame_rate", "30/1")
                if "/" in r_fps:
                    num, den = r_fps.split("/")
                    fps = round(float(num) / float(den), 2)
                else:
                    fps = float(r_fps)
                if not duration and "duration" in s:
                    duration = float(s["duration"])
                break

        return {
            "width": width,
            "height": height,
            "fps": fps,
            "duration": duration,
        }

    def generate_proxies(self, master_path: Path) -> Tuple[Path, Path]:
        """Generate 16kHz mono .wav and 480p low-bitrate proxy .mp4."""
        ffmpeg = self._get_ffmpeg_cmd()
        stem = master_path.stem
        wav_path = self.audio_dir / f"{stem}_16k_mono.wav"
        proxy_path = self.proxies_dir / f"{stem}_proxy_480p.mp4"

        # 1. Extract 16kHz mono WAV for audio & whisper processing
        if not wav_path.exists():
            logger.info(f"Extracting 16kHz mono WAV: {wav_path.name}")
            cmd_wav = [
                ffmpeg,
                "-y",
                "-loglevel", "error",
                "-i", str(master_path),
                "-vn",
                "-acodec", "pcm_s16le",
                "-ar", "16000",
                "-ac", "1",
                str(wav_path),
            ]
            subprocess.run(cmd_wav, capture_output=True, check=True)

        # 2. Extract 480p proxy MP4 for computer vision & scene cut analysis
        if not proxy_path.exists():
            logger.info(f"Generating 480p low-bitrate proxy: {proxy_path.name}")
            cmd_proxy = [
                ffmpeg,
                "-y",
                "-loglevel", "error",
                "-i", str(master_path),
                "-vf", "scale=-2:480",
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "28",
                "-c:a", "aac",
                "-b:a", "64k",
                str(proxy_path),
            ]
            subprocess.run(cmd_proxy, capture_output=True, check=True)

        return wav_path, proxy_path

    def _init_whisper(self):
        """Lazy load Faster-Whisper model."""
        if self._whisper_model is None:
            settings = get_settings()
            try:
                from faster_whisper import WhisperModel
                import torch
                device = "cuda" if torch.cuda.is_available() else "cpu"
                compute_type = settings.whisper_compute_type if device == "cuda" else "int8"
                logger.info(f"Loading faster-whisper model '{settings.whisper_model_size}' on {device} ({compute_type})...")
                self._whisper_model = WhisperModel(
                    settings.whisper_model_size,
                    device=device,
                    compute_type=compute_type,
                )
            except Exception as e:
                logger.warning(f"Could not load faster-whisper GPU/model: {e}. Audio energy fallback will be used.")
                self._whisper_model = None

    def transcribe_audio(
        self, wav_path: Path, min_silence_sec: float = 0.25, total_duration: Optional[float] = None
    ) -> Tuple[List[WordToken], List[SilenceOrFillerSpan]]:
        """Run Faster-Whisper transcription with word-level timestamps and dead air detection."""
        self._init_whisper()
        words: List[WordToken] = []
        bad_spans: List[SilenceOrFillerSpan] = []

        if self._whisper_model is not None:
            try:
                segments, info = self._whisper_model.transcribe(
                    str(wav_path),
                    word_timestamps=True,
                    vad_filter=True,
                    vad_parameters=dict(min_silence_duration_ms=250),
                )

                prev_end = 0.0
                first_word = True
                for segment in segments:
                    if segment.words:
                        for w in segment.words:
                            clean_word = re.sub(r"[^\w\s]", "", w.word.strip()).lower()

                            # Initial dead air check before first word
                            if first_word:
                                if w.start >= min_silence_sec:
                                    bad_spans.append(
                                        SilenceOrFillerSpan(
                                            start_sec=0.0,
                                            end_sec=round(w.start, 3),
                                            duration_sec=round(w.start, 3),
                                            kind="dead_air",
                                        )
                                    )
                                first_word = False
                            else:
                                # Dead air check between words
                                gap = w.start - prev_end
                                if gap >= min_silence_sec and prev_end > 0.0:
                                    bad_spans.append(
                                        SilenceOrFillerSpan(
                                            start_sec=round(prev_end, 3),
                                            end_sec=round(w.start, 3),
                                            duration_sec=round(gap, 3),
                                            kind="dead_air",
                                        )
                                    )

                            # Filler word check
                            if clean_word in FILLER_WORDS:
                                bad_spans.append(
                                    SilenceOrFillerSpan(
                                        start_sec=round(w.start, 3),
                                        end_sec=round(w.end, 3),
                                        duration_sec=round(w.end - w.start, 3),
                                        kind="um_uh_filler",
                                    )
                                )

                            words.append(
                                WordToken(
                                    word=w.word.strip(),
                                    start_sec=round(w.start, 3),
                                    end_sec=round(w.end, 3),
                                    confidence=round(float(getattr(w, "probability", 0.95)), 3),
                                )
                            )
                            prev_end = w.end

                # Trailing dead air check after last word
                effective_duration = total_duration or (info.duration if info else None)
                if effective_duration and effective_duration > prev_end:
                    trailing_gap = effective_duration - prev_end
                    if trailing_gap >= min_silence_sec:
                        bad_spans.append(
                            SilenceOrFillerSpan(
                                start_sec=round(prev_end, 3),
                                end_sec=round(effective_duration, 3),
                                duration_sec=round(trailing_gap, 3),
                                kind="dead_air",
                            )
                        )
            except Exception as e:
                logger.error(f"Whisper transcription failed: {e}. Falling back to energy silence detector.")
                bad_spans = self._detect_silence_via_rms(wav_path, min_silence_sec)
        else:
            bad_spans = self._detect_silence_via_rms(wav_path, min_silence_sec)

        return words, bad_spans

    def _detect_silence_via_rms(
        self, wav_path: Path, min_silence_sec: float = 0.25, threshold_db: float = -38.0
    ) -> List[SilenceOrFillerSpan]:
        """Energy-based silence detector using WAV PCM chunks with exact dBFS calculation."""
        spans: List[SilenceOrFillerSpan] = []
        if not wav_path.exists():
            return spans

        with wave.open(str(wav_path), "rb") as wf:
            framerate = wf.getframerate()
            nchannels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            total_frames = wf.getnframes()

            if sampwidth != 2:
                return spans  # Only 16-bit PCM supported for raw struct unpack

            chunk_size = int(framerate * 0.05)  # 50ms chunks
            in_silence = False
            silence_start = 0.0
            cur_time = 0.0

            while True:
                frames = wf.readframes(chunk_size)
                if not frames:
                    break
                count = len(frames) // 2
                shorts = struct.unpack(f"{count}h", frames)
                # Compute RMS
                sum_sq = sum(s * s for s in shorts)
                rms = (sum_sq / count) ** 0.5 if count > 0 else 0
                # Convert to exact dBFS using log10
                ratio = (rms / 32768.0) if rms > 0 else 1e-9
                db = 20.0 * math.log10(ratio)

                is_silent = (db < threshold_db)
                if is_silent and not in_silence:
                    in_silence = True
                    silence_start = cur_time
                elif not is_silent and in_silence:
                    in_silence = False
                    dur = cur_time - silence_start
                    if dur >= min_silence_sec:
                        spans.append(
                            SilenceOrFillerSpan(
                                start_sec=round(silence_start, 3),
                                end_sec=round(cur_time, 3),
                                duration_sec=round(dur, 3),
                                kind="dead_air",
                            )
                        )
                cur_time += len(frames) / (framerate * sampwidth * nchannels)

            if in_silence:
                dur = cur_time - silence_start
                if dur >= min_silence_sec:
                    spans.append(
                        SilenceOrFillerSpan(
                            start_sec=round(silence_start, 3),
                            end_sec=round(cur_time, 3),
                            duration_sec=round(dur, 3),
                            kind="dead_air",
                        )
                    )

        return spans

    def detect_scenes(self, proxy_path: Path, total_duration: float) -> List[Tuple[float, float]]:
        """Detect scene boundaries using PySceneDetect or ffmpeg scene score filter."""
        shots: List[Tuple[float, float]] = []

        # Try scenedetect package if installed
        try:
            from scenedetect import VideoManager, SceneManager
            from scenedetect.detectors import ContentDetector

            video_manager = VideoManager([str(proxy_path)])
            scene_manager = SceneManager()
            scene_manager.add_detector(ContentDetector(threshold=27.0))
            video_manager.start()
            scene_manager.detect_scenes(frame_source=video_manager)
            scene_list = scene_manager.get_scene_list()

            for scene in scene_list:
                shots.append((scene[0].get_seconds(), scene[1].get_seconds()))
            video_manager.release()
            if shots:
                return shots
        except Exception:
            pass

        # Robust ffmpeg scene filter fallback
        ffmpeg = self._get_ffmpeg_cmd()
        cmd = [
            ffmpeg,
            "-i", str(proxy_path),
            "-filter:v", "select='gt(scene,0.3)',showinfo",
            "-f", "null",
            "-",
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        pts_times = [0.0]
        for line in proc.stderr.splitlines():
            if "pts_time:" in line:
                m = re.search(r"pts_time:([0-9.]+)", line)
                if m:
                    pts_times.append(float(m.group(1)))

        pts_times.append(total_duration)
        pts_times = sorted(list(set(pts_times)))

        for i in range(len(pts_times) - 1):
            s_in = pts_times[i]
            s_out = pts_times[i + 1]
            if s_out - s_in >= 0.5:
                shots.append((round(s_in, 3), round(s_out, 3)))

        if not shots and total_duration > 0:
            shots.append((0.0, round(total_duration, 3)))

        return shots

    def analyze_file(
        self,
        master_filepath: str,
        role: Literal["A_ROLL_MAIN", "B_ROLL", "SCREEN_RECORDING", "MUSIC", "SFX"] = "A_ROLL_MAIN",
    ) -> MediaFileAnalysis:
        """Run complete media analysis on master file."""
        master_path = Path(master_filepath).resolve()
        if not master_path.exists():
            raise FileNotFoundError(f"Master media file not found: {master_path}")

        file_id = f"file_{master_path.stem}_{os.path.getsize(master_path)}"
        meta = self.probe_media_file(master_path)
        wav_path, proxy_path = self.generate_proxies(master_path)

        words: List[WordToken] = []
        bad_spans: List[SilenceOrFillerSpan] = []

        if role in ("A_ROLL_MAIN", "SCREEN_RECORDING"):
            words, bad_spans = self.transcribe_audio(wav_path, total_duration=meta.get("duration"))

        scene_intervals = self.detect_scenes(proxy_path, meta["duration"])
        visual_shots: List[VisualShotAnalysis] = []

        for idx, (s_in, s_out) in enumerate(scene_intervals):
            visual_shots.append(
                VisualShotAnalysis(
                    shot_id=idx + 1,
                    source_file=str(master_path),
                    start_sec=s_in,
                    end_sec=s_out,
                    shot_scale="MCU" if role == "A_ROLL_MAIN" else "WS",
                    camera_motion="static",
                    visual_quality_score=8,
                    is_usable=True,
                    subject_emotion="neutral",
                    b_roll_tags=[master_path.stem.lower()],
                    summary=f"Detected shot segment {idx + 1} from {s_in}s to {s_out}s.",
                )
            )

        return MediaFileAnalysis(
            file_id=file_id,
            master_filepath=str(master_path),
            proxy_filepath=str(proxy_path),
            fps=meta["fps"],
            width=meta["width"],
            height=meta["height"],
            duration_sec=round(meta["duration"], 3),
            role=role,
            words=words,
            bad_spans=bad_spans,
            shots=visual_shots,
        )
