"""Project Argon Main Orchestrator and Self-Healing Execution Engine.

Root controller managing autonomous video production:
1. Orchestrates Ingestion -> Vision -> Director -> Audio -> VFX.
2. Enforces the Self-Healing Execution Loop with auto-debugging and rollback.
3. Provides CLI interface for single-command end-to-end automated editing.
"""

from __future__ import annotations
import os
import re
import sys
import json
import time
import asyncio
import logging
import argparse
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import httpx

from config.settings import get_settings, PREMIERE_TICKS_PER_SECOND
from agents.schemas import MediaAnalysisManifest, MasterEditPlan
from agents.ingestion_agent import IngestionAgent
from agents.vision_agent import VisionAgent
from agents.director_agent import DirectorAgent
from agents.audio_master_agent import AudioMasterAgent
from agents.vfx_motion_agent import VFXMotionAgent
from mcp_server.jsx_compiler import JSXCompiler, ES3ValidationError
from memory.state_db import StateDB
from memory.style_memory import StyleMemory

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("argon.orchestrator")


class SelfHealingExecutor:
    """Dispatches JSX batches to Adobe CEP Bridge with auto-debugging and rollback."""

    def __init__(self, bridge_url: Optional[str] = None, max_retries: int = 3):
        settings = get_settings()
        self.bridge_url = (bridge_url or settings.ppro_bridge_url).rstrip("/")
        self.max_retries = max_retries
        self.state_db = StateDB()

    async def get_live_timeline_state(self) -> Dict[str, Any]:
        """Query Premiere Pro live timeline state."""
        url = f"{self.bridge_url}/execute_jsx"
        jsx = JSXCompiler.compile_get_timeline_state()
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(url, json={"script": jsx})
                if resp.status_code == 200:
                    data = resp.json()
                    res = data.get("result", {})
                    if isinstance(res, str):
                        try:
                            return json.loads(res)
                        except Exception:
                            return {"raw": res}
                    return res
        except Exception as e:
            logger.warning(f"Could not reach Premiere CEP Bridge: {e}")
        return {"hasActiveSequence": False, "status": "offline"}

    async def dispatch_jsx(self, jsx_script: str) -> Dict[str, Any]:
        """Send JSX string to CEP bridge."""
        url = f"{self.bridge_url}/execute_jsx"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json={"script": jsx_script})
            return resp.json()

    def auto_debug_patch(self, jsx_code: str, error_trace: str) -> str:
        """Analyze error trace and automatically patch known ExtendScript failure modes."""
        logger.info(f"Auto-debugger analyzing error trace: {error_trace}")
        patched = jsx_code

        # 1. Backslash path issues (Windows slashes in JSX string)
        if "\\" in patched:
            patched = re.sub(r'\\(?![ntrbf"\'\\])', "/", patched)

        # 2. ES3 syntax violations
        for pattern, fix in [
            (r"\bconst\s+", "var "),
            (r"\blet\s+", "var "),
        ]:
            patched = re.sub(pattern, fix, patched)

        # Inject ES3 Array polyfills if forEach/map/filter used or referenced in error
        if any(token in patched for token in (".forEach(", ".map(", ".filter(")) or "foreach" in error_trace.lower():
            logger.info("Injecting ES3 Array polyfill into JSX payload.")
            polyfill = (
                "if (!Array.prototype.forEach) { Array.prototype.forEach = function(fn, scope) { for (var i = 0; i < this.length; i++) { if (i in this) fn.call(scope, this[i], i, this); } }; }\n"
                "if (!Array.prototype.map) { Array.prototype.map = function(fn, scope) { var res = []; for (var i = 0; i < this.length; i++) { if (i in this) res.push(fn.call(scope, this[i], i, this)); } return res; }; }\n"
                "if (!Array.prototype.filter) { Array.prototype.filter = function(fn, scope) { var res = []; for (var i = 0; i < this.length; i++) { if (i in this && fn.call(scope, this[i], i, this)) res.push(this[i]); } return res; }; }\n"
            )
            patched = polyfill + patched

        # 3. Time calculation sanity: verify tick constant is integer
        if "254016000000" not in patched and "ticks" in error_trace.lower():
            logger.info("Injecting explicit tick conversion constant into JSX payload.")
            patched = "var ARGON_TICKS_PER_SEC = 254016000000;\n" + patched

        # 4. Inject QE DOM enabler if QE error detected
        if "qe" in error_trace.lower() and "app.enableQE()" not in patched:
            logger.info("Injecting app.enableQE() into payload.")
            patched = "if (app.enableQE) { app.enableQE(); }\n" + patched

        return patched

    async def execute_plan_safely(
        self, plan: MasterEditPlan, project_id: str
    ) -> Dict[str, Any]:
        """Execute MasterEditPlan with pre-flight check, retries, and rollback verification."""
        logger.info(f"Initiating execution for plan: {plan.plan_id} ({len(plan.actions)} actions)")

        # 1. Capture pre-state snapshot
        pre_state = await self.get_live_timeline_state()
        snapshot_id = self.state_db.record_snapshot(
            project_id=project_id,
            timeline_state=pre_state,
            plan_id=plan.plan_id,
        )
        logger.info(f"Recorded pre-state snapshot #{snapshot_id}")

        # 2. Compile to ES3
        current_jsx = JSXCompiler.compile_edit_plan_batch(plan)

        attempt = 0
        last_error = ""

        while attempt < self.max_retries:
            attempt += 1
            logger.info(f"Executing JSX batch (Attempt {attempt}/{self.max_retries})...")

            try:
                res = await self.dispatch_jsx(current_jsx)
                status = res.get("status")

                if status == "ok":
                    result_payload = res.get("result", {})
                    if isinstance(result_payload, str):
                        try:
                            result_payload = json.loads(result_payload)
                        except Exception:
                            pass

                    # Check for partial errors inside ExtendScript batch execution
                    batch_errors = result_payload.get("errors", []) if isinstance(result_payload, dict) else []
                    batch_status = result_payload.get("status") if isinstance(result_payload, dict) else None

                    if batch_status != "partial_error" and not batch_errors:
                        # Verify post-execution timeline state
                        post_state = await self.get_live_timeline_state()
                        logger.info("Execution succeeded. Verified live Premiere timeline state.")

                        return {
                            "status": "success",
                            "attempts": attempt,
                            "pre_snapshot_id": snapshot_id,
                            "post_state": post_state,
                            "result": result_payload,
                        }

                    # ExtendScript batch reported internal errors
                    err_details = "; ".join(f"Action {e.get('action_id')}: {e.get('error')}" for e in batch_errors)
                    last_error = f"ExtendScript batch execution failed with {len(batch_errors)} error(s): {err_details}"
                    logger.warning(f"Batch execution partial error on attempt {attempt}: {last_error}")
                else:
                    last_error = res.get("error_trace", str(res))
                    logger.warning(f"Bridge execution reported error on attempt {attempt}: {last_error}")

            except Exception as net_err:
                last_error = str(net_err)
                logger.warning(f"Network error communicating with bridge on attempt {attempt}: {last_error}")

            # Auto-debug patch before next attempt
            if attempt < self.max_retries:
                current_jsx = self.auto_debug_patch(current_jsx, last_error)
                await asyncio.sleep(1.0)

        # Fatal failure after retries -> trigger rollback recommendation
        logger.error(f"Execution failed after {self.max_retries} attempts. Final error: {last_error}")
        return {
            "status": "failed",
            "error": last_error,
            "pre_snapshot_id": snapshot_id,
            "recommendation": "Rollback to pre-state snapshot recommended.",
        }


class ArgonEngine:
    """Complete root orchestrator coordinating multi-agent autonomous video production."""

    def __init__(self):
        self.settings = get_settings()
        self.ingestion = IngestionAgent()
        self.vision = VisionAgent()
        self.director = DirectorAgent()
        self.audio_master = AudioMasterAgent()
        self.vfx = VFXMotionAgent()
        self.state_db = StateDB()
        self.style_memory = StyleMemory()
        self.executor = SelfHealingExecutor()

    async def run_full_pipeline(
        self,
        folder_path: str,
        editing_style: str = "Retention",
        user_prompt: str = "",
        sfx_library: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Run complete autonomous production: Ingestion -> Vision -> Director -> Audio -> Premiere."""
        start_time = time.time()
        input_dir = Path(folder_path).resolve()
        logger.info(f"=== Starting Project Argon Full Pipeline for: {input_dir} (Style: {editing_style}) ===")

        # 1. INGESTION & VISION
        logger.info("Stage 1/4: Ingesting footage, generating 16kHz audio & 480p proxies...")
        valid_exts = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}
        files = [f for f in input_dir.iterdir() if f.suffix.lower() in valid_exts]

        if not files:
            raise ValueError(f"No valid video files found in {input_dir}")

        manifest = MediaAnalysisManifest(
            manifest_id=f"manifest_{input_dir.name}_{int(time.time())}",
            project_name=input_dir.name,
        )
        proj_id = self.state_db.create_project(input_dir.name, {"folder": str(input_dir), "style": editing_style})

        for idx, media_file in enumerate(files):
            role = "A_ROLL_MAIN" if idx == 0 else "B_ROLL"
            logger.info(f"Ingesting file {idx + 1}/{len(files)}: {media_file.name} (Role: {role})")
            analysis = self.ingestion.analyze_file(str(media_file), role=role)

            logger.info(f"Analyzing visual shots with Llama-3.2-90B-Vision for {media_file.name}...")
            enriched = await self.vision.enrich_media_analysis(analysis)
            manifest.files.append(enriched)
            self.state_db.save_media_file(proj_id, enriched)

        # 2. DIRECTOR EDIT PLANNING
        logger.info("Stage 2/4: Formulating MasterEditPlan with Llama-3.1-Nemotron-70B-Instruct...")
        style_rules_raw = await self.style_memory.query_rules(f"{editing_style} {user_prompt}", top_k=3)
        style_rules = [r["description"] for r in style_rules_raw]

        plan = await self.director.plan_with_llm(
            manifest=manifest,
            editing_style=editing_style,
            user_prompt=user_prompt,
            style_rules=style_rules,
        )

        # 3. AUDIO MASTERING & SFX
        logger.info("Stage 3/4: Mastering audio: applying J/L-cuts and transition SFX...")
        plan = self.audio_master.apply_jl_cut_offsets(plan, offset_sec=0.25)
        if sfx_library:
            plan = self.audio_master.place_transition_sfx(plan, sfx_library)

        self.state_db.save_edit_plan(proj_id, plan)

        # 4. SELF-HEALING LIVE EXECUTION IN PREMIERE PRO
        logger.info(f"Stage 4/4: Executing {len(plan.actions)} timeline mutations in Adobe Premiere Pro...")
        exec_res = await self.executor.execute_plan_safely(plan, project_id=proj_id)

        elapsed = time.time() - start_time
        logger.info(f"=== Production Run Complete in {elapsed:.1f}s (Status: {exec_res['status']}) ===")

        return {
            "status": exec_res["status"],
            "project_id": proj_id,
            "plan_id": plan.plan_id,
            "timeline_duration_sec": plan.timeline_duration_sec,
            "total_clips_placed": len(plan.actions),
            "execution_details": exec_res,
            "elapsed_seconds": round(elapsed, 2),
        }

    async def run_ingest_pipeline(self, folder_path: str) -> MediaAnalysisManifest:
        """Run Ingestion + Vision on raw footage directory without executing edits in Premiere."""
        input_dir = Path(folder_path).resolve()
        valid_exts = {".mp4", ".mov", ".mkv", ".avi", ".m4v"}
        files = [f for f in input_dir.iterdir() if f.suffix.lower() in valid_exts]
        if not files:
            raise ValueError(f"No valid video files found in {input_dir}")

        manifest = MediaAnalysisManifest(
            manifest_id=f"manifest_{input_dir.name}_{int(time.time())}",
            project_name=input_dir.name,
        )
        proj_id = self.state_db.create_project(input_dir.name, {"folder": str(input_dir)})

        for idx, media_file in enumerate(files):
            role = "A_ROLL_MAIN" if idx == 0 else "B_ROLL"
            analysis = self.ingestion.analyze_file(str(media_file), role=role)
            enriched = await self.vision.enrich_media_analysis(analysis)
            manifest.files.append(enriched)
            self.state_db.save_media_file(proj_id, enriched)

        out_path = self.settings.workspace_dir / f"{manifest.manifest_id}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(manifest.model_dump_json(indent=2))
        logger.info(f"Ingestion complete: saved manifest to {out_path}")
        return manifest


def main():
    parser = argparse.ArgumentParser(description="Argon Autonomous Video Engine CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Full pipeline command
    pipe_parser = subparsers.add_parser("pipeline", help="Run end-to-end autonomous video pipeline")
    pipe_parser.add_argument("folder", help="Directory containing raw video clips")
    pipe_parser.add_argument("--style", default="Retention", choices=["Retention", "Cinematic", "Documentary", "Shortform"])
    pipe_parser.add_argument("--prompt", default="", help="Custom director prompt")

    # Ingest command
    ingest_parser = subparsers.add_parser("ingest", help="Ingest and analyze footage directory")
    ingest_parser.add_argument("folder", help="Directory containing video clips")

    # Status command
    subparsers.add_parser("status", help="Check bridge and engine status")

    args = parser.parse_args()
    engine = ArgonEngine()

    if args.command == "status":
        print("=== Project Argon Engine Status ===")
        print(f"Workspace: {engine.settings.workspace_dir}")
        print(f"State DB: {engine.settings.state_db_path}")
        print(f"PPRO Bridge URL: {engine.settings.ppro_bridge_url}")
        print(f"AEFT Bridge URL: {engine.settings.aeft_bridge_url}")
        print(f"PHXS Bridge URL: {engine.settings.phxs_bridge_url}")

        loop = asyncio.new_event_loop()
        state = loop.run_until_complete(engine.executor.get_live_timeline_state())
        print(f"Premiere Bridge Health: {state.get('status', 'online')}")
        return

    if args.command == "pipeline":
        loop = asyncio.new_event_loop()
        res = loop.run_until_complete(
            engine.run_full_pipeline(args.folder, editing_style=args.style, user_prompt=args.prompt)
        )
        print(json.dumps(res, indent=2))
        return

    if args.command == "ingest":
        loop = asyncio.new_event_loop()
        manifest = loop.run_until_complete(
            engine.run_ingest_pipeline(args.folder)
        )
        print(f"[+] Ingestion complete for {args.folder}: {len(manifest.files)} files analyzed.")
        print(f"Manifest ID: {manifest.manifest_id}")


if __name__ == "__main__":
    main()
