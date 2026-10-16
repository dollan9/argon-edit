"""Settings and system configuration for Argon Video Engine.

Implements strict validation and the Premiere Ticks Law:
1 Second = 254016000000 Ticks.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Optional, Union
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# Load local .env if available
load_dotenv()

# ==============================================================================
# TECHNICAL CONSTANTS (THE PREMIERE TICKS LAW)
# ==============================================================================
PREMIERE_TICKS_PER_SECOND: int = 254016000000


def seconds_to_ticks(seconds: float) -> int:
    """Convert float seconds into exact Premiere Pro ticks (integer)."""
    return int(round(float(seconds) * PREMIERE_TICKS_PER_SECOND))


def seconds_to_ticks_str(seconds: float) -> str:
    """Convert float seconds into Premiere Pro ticks string for ExtendScript Time objects."""
    return str(seconds_to_ticks(seconds))


def ticks_to_seconds(ticks: Union[int, str, float]) -> float:
    """Convert Premiere Pro ticks into float seconds."""
    return float(ticks) / PREMIERE_TICKS_PER_SECOND


# ==============================================================================
# SYSTEM SETTINGS MODEL
# ==============================================================================
class ArgonSettings(BaseModel):
    """Runtime configuration for Project Argon Video Engine."""

    # API Keys & NIM endpoints
    nvidia_api_key: str = Field(
        default_factory=lambda: os.getenv("NVIDIA_API_KEY", "")
    )
    nvidia_base_url: str = Field(
        default_factory=lambda: os.getenv(
            "NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"
        )
    )

    # Models
    director_model: str = Field(
        default_factory=lambda: os.getenv(
            "DIRECTOR_MODEL", "nvidia/llama-3.1-nemotron-70b-instruct"
        )
    )
    director_fallback_model: str = Field(
        default_factory=lambda: os.getenv(
            "DIRECTOR_FALLBACK_MODEL", "meta/llama-3.3-70b-instruct"
        )
    )
    vision_model: str = Field(
        default_factory=lambda: os.getenv(
            "VISION_MODEL", "meta/llama-3.2-90b-vision-instruct"
        )
    )
    embedding_model: str = Field(
        default_factory=lambda: os.getenv(
            "EMBEDDING_MODEL", "nvidia/nv-embedqa-e5-v5"
        )
    )
    whisper_model_size: str = Field(
        default_factory=lambda: os.getenv("WHISPER_MODEL_SIZE", "large-v3-turbo")
    )
    whisper_compute_type: str = Field(
        default_factory=lambda: os.getenv("WHISPER_COMPUTE_TYPE", "float16")
    )

    # CEP Bridge Ports
    ppro_bridge_port: int = Field(
        default_factory=lambda: int(os.getenv("PPRO_BRIDGE_PORT", "8088"))
    )
    aeft_bridge_port: int = Field(
        default_factory=lambda: int(os.getenv("AEFT_BRIDGE_PORT", "8089"))
    )
    phxs_bridge_port: int = Field(
        default_factory=lambda: int(os.getenv("PHXS_BRIDGE_PORT", "8090"))
    )

    # Bridge URLs
    ppro_bridge_url: str = Field(
        default_factory=lambda: os.getenv(
            "PPRO_BRIDGE_URL", f"http://localhost:{os.getenv('PPRO_BRIDGE_PORT', '8088')}"
        )
    )
    aeft_bridge_url: str = Field(
        default_factory=lambda: os.getenv(
            "AEFT_BRIDGE_URL", f"http://localhost:{os.getenv('AEFT_BRIDGE_PORT', '8089')}"
        )
    )
    phxs_bridge_url: str = Field(
        default_factory=lambda: os.getenv(
            "PHXS_BRIDGE_URL", f"http://localhost:{os.getenv('PHXS_BRIDGE_PORT', '8090')}"
        )
    )

    # File and Directory Paths
    workspace_dir: Path = Field(
        default_factory=lambda: Path(os.getenv("WORKSPACE_DIR", "./workspace")).resolve()
    )
    state_db_path: Path = Field(
        default_factory=lambda: Path(os.getenv("STATE_DB_PATH", "./data/argon_state.db")).resolve()
    )
    style_memory_dir: Path = Field(
        default_factory=lambda: Path(os.getenv("STYLE_MEMORY_DIR", "./data/style_memory")).resolve()
    )

    # Adobe Executable Paths
    premiere_path: Optional[str] = Field(
        default_factory=lambda: os.getenv(
            "PREMIERE_PATH",
            "C:/Program Files/Adobe/Adobe Premiere Pro 2024/Adobe Premiere Pro.exe",
        )
    )
    aftereffects_path: Optional[str] = Field(
        default_factory=lambda: os.getenv(
            "AFTEREFFECTS_PATH",
            "C:/Program Files/Adobe/Adobe After Effects 2024/Support Files/AfterFX.exe",
        )
    )
    photoshop_path: Optional[str] = Field(
        default_factory=lambda: os.getenv(
            "PHOTOSHOP_PATH",
            "C:/Program Files/Adobe/Adobe Photoshop 2024/Photoshop.exe",
        )
    )

    # Production Defaults
    audio_lufs_target: float = Field(
        default_factory=lambda: float(os.getenv("AUDIO_LUFS_TARGET", "-14.0"))
    )
    max_worker_concurrency: int = Field(
        default_factory=lambda: int(os.getenv("MAX_WORKER_CONCURRENCY", "2"))
    )
    default_pacing_blueprint: str = Field(
        default_factory=lambda: os.getenv("DEFAULT_PACING_BLUEPRINT", "Retention")
    )

    def ensure_directories(self) -> None:
        """Create necessary working directories safely."""
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        self.state_db_path.parent.mkdir(parents=True, exist_ok=True)
        self.style_memory_dir.mkdir(parents=True, exist_ok=True)


_global_settings: Optional[ArgonSettings] = None


def get_settings() -> ArgonSettings:
    """Retrieve or initialize singleton ArgonSettings instance."""
    global _global_settings
    if _global_settings is None:
        _global_settings = ArgonSettings()
        _global_settings.ensure_directories()
    return _global_settings
