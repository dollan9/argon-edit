"""State and Project SQLite Memory Database for Project Argon.

Maintains transactional state tracking, ingested footage metadata,
atomic edit actions, and undo snapshots for self-healing execution rollbacks.
"""

from __future__ import annotations
import sqlite3
import json
import logging
from pathlib import Path
from typing import Optional, List, Dict, Any
from datetime import datetime, timezone

from config.settings import get_settings
from agents.schemas import MediaFileAnalysis, MasterEditPlan, TimelineClipAction

logger = logging.getLogger("argon.memory.state")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


from contextlib import contextmanager


class StateDB:
    """Thread-safe SQLite manager for project lifecycle, timeline mutations, and undo history."""

    def __init__(self, db_path: Optional[Path] = None):
        settings = get_settings()
        self.db_path = db_path or settings.state_db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_tables()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_tables(self) -> None:
        """Create database schema if not present."""
        with self._get_connection() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    metadata_json TEXT
                );

                CREATE TABLE IF NOT EXISTS media_files (
                    file_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    master_path TEXT NOT NULL,
                    proxy_path TEXT NOT NULL,
                    role TEXT NOT NULL,
                    duration_sec REAL NOT NULL,
                    analysis_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );

                CREATE TABLE IF NOT EXISTS edit_plans (
                    plan_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    duration_sec REAL NOT NULL,
                    plan_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );

                CREATE TABLE IF NOT EXISTS timeline_actions (
                    action_id INTEGER PRIMARY KEY,
                    plan_id TEXT NOT NULL,
                    track_type TEXT NOT NULL,
                    track_index INTEGER NOT NULL,
                    master_filepath TEXT NOT NULL,
                    src_in_sec REAL NOT NULL,
                    src_out_sec REAL NOT NULL,
                    timeline_in_sec REAL NOT NULL,
                    status TEXT NOT NULL,
                    reasoning TEXT,
                    executed_at TEXT,
                    FOREIGN KEY(plan_id) REFERENCES edit_plans(plan_id)
                );

                CREATE TABLE IF NOT EXISTS timeline_snapshots (
                    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL,
                    plan_id TEXT,
                    timeline_state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(project_id) REFERENCES projects(project_id)
                );
            """)

    def create_project(self, name: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Initialize a new video project entry."""
        now = datetime.now(timezone.utc).isoformat()
        proj_id = f"proj_{name.lower().replace(' ', '_')}_{int(datetime.now().timestamp())}"
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO projects (project_id, name, status, created_at, updated_at, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (proj_id, name, "active", now, now, json.dumps(metadata or {})),
            )
        logger.info(f"Created project: {name} ({proj_id})")
        return proj_id

    def save_media_file(self, project_id: str, analysis: MediaFileAnalysis) -> None:
        """Save media analysis manifest row."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO media_files
                (file_id, project_id, master_path, proxy_path, role, duration_sec, analysis_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    analysis.file_id,
                    project_id,
                    analysis.master_filepath,
                    analysis.proxy_filepath,
                    analysis.role,
                    analysis.duration_sec,
                    analysis.model_dump_json(),
                    now,
                ),
            )

    def save_edit_plan(self, project_id: str, plan: MasterEditPlan) -> None:
        """Persist MasterEditPlan and its actions."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO edit_plans
                (plan_id, project_id, title, duration_sec, plan_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    plan.plan_id,
                    project_id,
                    plan.project_title,
                    plan.timeline_duration_sec,
                    plan.model_dump_json(),
                    now,
                ),
            )

            for act in plan.actions:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO timeline_actions
                    (action_id, plan_id, track_type, track_index, master_filepath, src_in_sec, src_out_sec, timeline_in_sec, status, reasoning)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        act.action_id,
                        plan.plan_id,
                        act.track_type,
                        act.track_index,
                        act.master_filepath,
                        act.src_in_sec,
                        act.src_out_sec,
                        act.timeline_in_sec,
                        "pending",
                        act.reasoning,
                    ),
                )

    def record_snapshot(
        self, project_id: str, timeline_state: Dict[str, Any], plan_id: Optional[str] = None
    ) -> int:
        """Capture live timeline state for rollback verification."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO timeline_snapshots (project_id, plan_id, timeline_state_json, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (project_id, plan_id, json.dumps(timeline_state), now),
            )
            return cursor.lastrowid

    def get_latest_snapshot(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve the most recent timeline state snapshot."""
        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT timeline_state_json FROM timeline_snapshots
                WHERE project_id = ?
                ORDER BY snapshot_id DESC LIMIT 1
                """,
                (project_id,),
            ).fetchone()
            if row:
                return json.loads(row["timeline_state_json"])
        return None

    def mark_action_status(self, action_id: int, status: str = "success") -> None:
        """Update action execution status."""
        now = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            conn.execute(
                """
                UPDATE timeline_actions
                SET status = ?, executed_at = ?
                WHERE action_id = ?
                """,
                (status, now, action_id),
            )
