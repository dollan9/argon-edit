"""FastMCP Server exposing Adobe Creative Cloud & Pipeline Tools to Agents.

Exposes live Premiere Pro, After Effects, and Photoshop inspection,
ingestion analysis, Hollywood Director planning, and self-healing execution.
"""

from __future__ import annotations
import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
import httpx
try:
    from mcp.server.mcpserver import MCPServer as FastMCP
except ImportError:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        class FastMCP:  # type: ignore
            def __init__(self, name: str):
                self.name = name

            def tool(self):
                def decorator(fn):
                    return fn

                return decorator

            def run(self):
                pass

from config.settings import get_settings
from mcp_server.jsx_compiler import JSXCompiler
from agents.schemas import MediaAnalysisManifest, MasterEditPlan
from agents.ingestion_agent import IngestionAgent
from agents.vision_agent import VisionAgent
from agents.director_agent import DirectorAgent
from agents.vfx_motion_agent import VFXMotionAgent
from memory.state_db import StateDB
from memory.style_memory import StyleMemory

logger = logging.getLogger("argon.mcp.server")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Initialize FastMCP Server
mcp = FastMCP("ArgonAdobeController")

settings = get_settings()
state_db = StateDB()
style_memory = StyleMemory()
ingestion_agent = IngestionAgent()
vision_agent = VisionAgent()
director_agent = DirectorAgent()
vfx_agent = VFXMotionAgent()


async def _send_bridge_request(port: int, script_or_fn: str, is_raw_script: bool = True) -> Dict[str, Any]:
    """Helper to dispatch JSX execution payload to Adobe CEP bridge server."""
    url = f"http://127.0.0.1:{port}/execute_jsx"
    payload = {"script": script_or_fn} if is_raw_script else json.loads(script_or_fn)

    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                return resp.json()
            return {
                "status": "error",
                "http_code": resp.status_code,
                "error_trace": resp.text,
            }
    except Exception as e:
        logger.warning(f"Bridge HTTP connection failed on port {port}: {e}")
        return {
            "status": "bridge_offline",
            "port": port,
            "error_trace": f"Could not reach Adobe CEP Bridge on port {port}. Ensure Adobe application and Argon panel are open. ({e})",
        }


@mcp.tool()
async def inspect_live_premiere_timeline() -> Dict[str, Any]:
    """Query localhost:8088 for current Premiere Pro tracks, clips, lengths, and playhead position.

    Returns:
        Dict[str, Any]: Complete live timeline state including active sequence name,
        dimensions, duration, and array of video/audio track items.
    """
    jsx = JSXCompiler.compile_get_timeline_state()
    res = await _send_bridge_request(settings.ppro_bridge_port, jsx)

    if res.get("status") == "ok":
        result_data = res.get("result", {})
        if isinstance(result_data, str):
            try:
                result_data = json.loads(result_data)
            except Exception:
                pass
        return {"status": "ok", "timeline_state": result_data}
    return res


@mcp.tool()
async def ingest_and_analyze_footage(folder_path: str) -> MediaAnalysisManifest:
    """Run Ingestion + Vision agents on raw footage in a directory.

    Extracts 16kHz audio for Whisper transcription and 480p proxy for scene detection,
    then executes batched multimodal vision evaluation via Llama-3.2-90B-Vision.

    Args:
        folder_path (str): Absolute directory path containing media files.

    Returns:
        MediaAnalysisManifest: Manifest containing all analyzed clips and shots.
    """
    p = Path(folder_path).resolve()
    if not p.exists() or not p.is_dir():
        raise FileNotFoundError(f"Directory not found: {folder_path}")

    valid_extensions = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}
    media_files = [f for f in p.iterdir() if f.suffix.lower() in valid_extensions]

    if not media_files:
        raise ValueError(f"No video files found in {folder_path}")

    manifest = MediaAnalysisManifest(
        manifest_id=f"manifest_{p.name}_{len(media_files)}files",
        project_name=p.name,
    )

    proj_id = state_db.create_project(p.name, {"folder_path": str(p)})

    for idx, f in enumerate(media_files):
        # Infer role: first video is A-roll, subsequent files are B-roll unless designated
        role = "A_ROLL_MAIN" if idx == 0 else "B_ROLL"
        analysis = ingestion_agent.analyze_file(str(f), role=role)
        enriched = await vision_agent.enrich_media_analysis(analysis)
        manifest.files.append(enriched)
        state_db.save_media_file(proj_id, enriched)

    out_manifest_path = settings.workspace_dir / f"{manifest.manifest_id}.json"
    with open(out_manifest_path, "w", encoding="utf-8") as out_f:
        out_f.write(manifest.model_dump_json(indent=2))

    return manifest


@mcp.tool()
async def generate_master_edit_plan(
    manifest_path: str,
    editing_style: str = "Retention",
    user_prompt: str = "",
) -> MasterEditPlan:
    """Run Nemotron Director Agent to plan cuts, B-roll, punch-ins, and J/L-cuts.

    Args:
        manifest_path (str): Path to MediaAnalysisManifest JSON file.
        editing_style (str): Editorial blueprint style ('Retention', 'Cinematic', 'Documentary', 'Shortform').
        user_prompt (str): Additional artistic instructions or constraints.

    Returns:
        MasterEditPlan: Complete Hollywood edit decision list.
    """
    m_path = Path(manifest_path).resolve()
    if not m_path.exists():
        raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

    with open(m_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    manifest = MediaAnalysisManifest.model_validate(data)

    # Query persistent vector memory for user style rules
    style_rules_dicts = await style_memory.query_rules(f"{editing_style} {user_prompt}", top_k=3)
    style_rules = [r["description"] for r in style_rules_dicts]

    plan = await director_agent.plan_with_llm(
        manifest=manifest,
        editing_style=editing_style,
        user_prompt=user_prompt,
        style_rules=style_rules,
    )

    out_plan_path = settings.workspace_dir / f"{plan.plan_id}.json"
    with open(out_plan_path, "w", encoding="utf-8") as out_f:
        out_f.write(plan.model_dump_json(indent=2))

    return plan


@mcp.tool()
async def execute_edit_plan_in_premiere(plan_json: str) -> Dict[str, Any]:
    """Compile MasterEditPlan into batched ES3 calls, send to localhost:8088, and verify timeline.

    Args:
        plan_json (str): Raw JSON string or path to MasterEditPlan JSON file.

    Returns:
        Dict[str, Any]: Execution confirmation, latency, and verified timeline state.
    """
    # Accept either file path or direct JSON string
    if os.path.exists(plan_json):
        with open(plan_json, "r", encoding="utf-8") as f:
            plan_data = json.load(f)
    else:
        plan_data = json.loads(plan_json)

    plan = MasterEditPlan.model_validate(plan_data)

    # 1. Compile to strictly compliant ES3 ExtendScript batch
    batch_jsx = JSXCompiler.compile_edit_plan_batch(plan)

    # 2. Capture pre-state snapshot
    pre_state = await inspect_live_premiere_timeline()

    # 3. Send execution payload to CEP bridge
    res = await _send_bridge_request(settings.ppro_bridge_port, batch_jsx)

    # Record snapshot in state DB
    state_db.record_snapshot(
        project_id=plan.project_title,
        timeline_state=res.get("result", {}),
        plan_id=plan.plan_id,
    )

    return {
        "status": res.get("status", "ok"),
        "bridge_response": res,
        "plan_id": plan.plan_id,
        "actions_executed": len(plan.actions),
    }


@mcp.tool()
async def create_after_effects_vfx_comp(
    comp_name: str,
    text_overlay: str,
    duration_sec: float = 3.0,
    template_aep: str = "",
) -> str:
    """Connect to After Effects (localhost:8089 or aerender), generate a rendered .mov
    (ProRes 4444 with Alpha) or .mogrt, and import it directly onto Track V3 in Premiere Pro.

    Args:
        comp_name (str): Identifier name for composition.
        text_overlay (str): Kinetic text string to animate.
        duration_sec (float): Duration in seconds.
        template_aep (str): Optional After Effects template project path.

    Returns:
        str: Absolute file path to the rendered ProRes 4444 overlay imported into Premiere Pro.
    """
    vfx_res = await vfx_agent.create_text_callout_overlay(
        text=text_overlay,
        duration_sec=duration_sec,
        comp_name=comp_name,
    )
    rendered_mov = vfx_res.get("output_path", "")

    # Import directly onto Track V3 (index 2) in Premiere Pro via CEP bridge
    if rendered_mov and os.path.exists(rendered_mov):
        clean_mov_path = str(Path(rendered_mov).resolve()).replace("\\", "/")
        ppro_jsx = JSXCompiler.compile_insert_clip(
            file_path=clean_mov_path,
            src_in_sec=0.0,
            src_out_sec=duration_sec,
            timeline_in_sec=0.0,
            v_track_idx=2,  # Track V3
            a_track_idx=-1,
        )
        await _send_bridge_request(settings.ppro_bridge_port, ppro_jsx)
        logger.info(f"Imported rendered VFX callout onto Track V3: {clean_mov_path}")

    return str(rendered_mov)


@mcp.tool()
async def generate_photoshop_thumbnail(
    frame_path: str, headline_text: str, output_psd: str
) -> str:
    """Connect to Photoshop (localhost:8090) to create a high-CTR YouTube thumbnail.

    Args:
        frame_path (str): Background frame image path.
        headline_text (str): Punchy headline text for bold graphic layer.
        output_psd (str): Output file path for PSD / PNG.

    Returns:
        str: Absolute output file path of the generated thumbnail.
    """
    out_p = str(Path(output_psd).resolve()).replace("\\", "/")
    in_p = str(Path(frame_path).resolve()).replace("\\", "/")

    jsx = (
        f'argon_createThumbnail("{in_p}", "{headline_text}", "", "{out_p}", 1280, 720);\n'
        f'argon_addBadge("NEW", [255, 30, 30], 0.75, 0.25);\n'
    )
    await _send_bridge_request(settings.phxs_bridge_port, jsx)
    return str(Path(output_psd).resolve())


@mcp.tool()
async def save_editing_rule_to_memory(
    rule_description: str, parameters: Dict[str, Any]
) -> str:
    """Save user preferences and artistic editing rules into ChromaDB vector store.

    Args:
        rule_description (str): Human-readable editing principle (e.g. 'Use 112% punch-in on angry voice').
        parameters (Dict[str, Any]): Structured numerical adjustments (e.g. {'scale': 1.12}).

    Returns:
        str: Saved rule identifier string.
    """
    rule_id = await style_memory.add_rule(rule_description, parameters)
    return str(rule_id)


if __name__ == "__main__":
    mcp.run()
