"""VFX and Motion Graphics Agent for Project Argon.

Generates dynamic typography, callout animations, lower-thirds, and MOGRTs
via After Effects CEP Bridge (localhost:8089) or aerender CLI, outputting
ProRes 4444 with Alpha for Track V3 overlays in Premiere Pro.
"""

from __future__ import annotations
import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
import httpx

from config.settings import get_settings
from mcp_server.jsx_compiler import JSXCompiler

logger = logging.getLogger("argon.agents.vfx")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


class VFXMotionAgent:
    """Controls After Effects dynamic text overlays, motion templates, and ProRes renders."""

    def __init__(self, bridge_url: Optional[str] = None):
        settings = get_settings()
        self.bridge_url = bridge_url or settings.aeft_bridge_url
        self.output_dir = settings.workspace_dir / "vfx_renders"
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def execute_ae_jsx(self, jsx_code: str) -> Dict[str, Any]:
        """Send JSX execution string to After Effects CEP bridge on port 8089."""
        url = f"{self.bridge_url}/execute_jsx"
        payload = {"script": jsx_code}
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            logger.warning(f"After Effects bridge call failed ({e}). Returning offline mock response.")
            return {"status": "offline", "message": str(e)}

    async def create_text_callout_overlay(
        self,
        text: str,
        duration_sec: float = 3.0,
        font_size: int = 72,
        comp_name: Optional[str] = None,
        font_color: Optional[list] = None,
        anim_type: str = "kinetic",
    ) -> Dict[str, Any]:
        """Create an animated text callout in After Effects and render ProRes 4444 with alpha."""
        c_name = comp_name or f"VFX_Callout_{abs(hash(text)) % 10000}"
        out_mov = self.output_dir / f"{c_name}_alpha.mov"
        color_arr = font_color or [1.0, 0.85, 0.0]  # High retention gold

        esc_c_name = JSXCompiler._escape_js_string(c_name)
        esc_text = JSXCompiler._escape_js_string(text)
        esc_mov = JSXCompiler._escape_js_string(str(out_mov))
        esc_anim = JSXCompiler._escape_js_string(anim_type)

        jsx = (
            f'argon_createComp("{esc_c_name}", 1920, 1080, 30.0, {duration_sec});\n'
            f'argon_addTextLayer("{esc_c_name}", "{esc_text}", {font_size}, {json.dumps(color_arr)}, 0.5, 0.8, "{esc_anim}");\n'
            f'argon_renderComp("{esc_c_name}", "{esc_mov}", "Lossless with Alpha");\n'
        )

        res = await self.execute_ae_jsx(jsx)
        return {
            "comp_name": c_name,
            "text": text,
            "duration_sec": duration_sec,
            "output_path": str(out_mov),
            "bridge_response": res,
        }

    async def create_mogrt_callout(
        self,
        headline: str,
        subtitle: str,
        duration_sec: float = 3.0,
    ) -> Path:
        """Create a kinetic lower-third or MOGRT package."""
        mogrt_path = self.output_dir / f"mogrt_{abs(hash(headline)) % 10000}.mogrt"
        comp_name = f"MOGRT_Comp_{abs(hash(headline)) % 10000}"

        esc_comp = JSXCompiler._escape_js_string(comp_name)
        esc_head = JSXCompiler._escape_js_string(headline)
        esc_sub = JSXCompiler._escape_js_string(subtitle)
        esc_mogrt = JSXCompiler._escape_js_string(str(mogrt_path))

        jsx = (
            f'argon_createComp("{esc_comp}", 1920, 1080, 30.0, {duration_sec});\n'
            f'argon_addTextLayer("{esc_comp}", "{esc_head}", 80, [1,1,1], 0.5, 0.75, "pop");\n'
            f'argon_addTextLayer("{esc_comp}", "{esc_sub}", 42, [0.9,0.9,0.9], 0.5, 0.85, "static");\n'
            f'argon_exportMogrt("{esc_comp}", "{esc_mogrt}");\n'
        )
        await self.execute_ae_jsx(jsx)
        return mogrt_path
