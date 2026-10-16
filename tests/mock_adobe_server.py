"""Mock Adobe CEP Bridge HTTP Server for Local & CI/CD Testing.

Emulates Adobe Premiere Pro (8088), After Effects (8089), and Photoshop (8090)
CEP socket bridges without requiring Adobe Creative Cloud to be installed.
"""

from __future__ import annotations
import json
import logging
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from typing import List, Dict, Any, Optional

logger = logging.getLogger("argon.mock_adobe")


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """Multi-threaded HTTP server handling concurrent requests."""
    daemon_threads = True
    allow_reuse_address = True


class MockAdobeRequestHandler(BaseHTTPRequestHandler):
    """Simulates Adobe CEP Bridge responses for ExtendScript calls."""

    def log_message(self, format: str, *args: Any) -> None:
        """Suppress standard logging to keep test output clean."""
        pass

    def _send_json(self, status_code: int, data: Dict[str, Any]) -> None:
        payload = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()
        self.wfile.write(payload)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path in ("/health", "/"):
            port = self.server.server_address[1]
            app_map = {8088: "PPRO", 8089: "AEFT", 8090: "PHXS", 8084: "AUDT"}
            app_id = app_map.get(port, "PPRO")
            self._send_json(200, {
                "status": "ok",
                "appId": app_id,
                "port": port,
                "mock": True,
                "uptime_sec": 120.0,
                "queue_depth": 0,
            })
            return

        self._send_json(404, {"status": "error", "error": "Not Found"})

    def do_POST(self) -> None:
        if self.path in ("/execute_jsx", "/eval"):
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            try:
                data = json.loads(body)
            except Exception as e:
                self._send_json(400, {"status": "error", "error_trace": f"Invalid JSON: {e}"})
                return

            script = data.get("script") or ""
            fn_name = data.get("function_name") or ""
            full_code = f"{script} {fn_name}"

            # 1. Timeline State Query
            if "argon_getTimelineStateJSON" in full_code:
                timeline_state = {
                    "status": "ok",
                    "sequenceName": "Mock_Master_Timeline",
                    "fps": 23.976,
                    "playheadPositionSec": 0.0,
                    "playheadPositionTicks": "0",
                    "videoTracks": [
                        {"index": 0, "name": "Video 1", "clipCount": 0, "clips": []},
                        {"index": 1, "name": "Video 2", "clipCount": 0, "clips": []},
                        {"index": 2, "name": "Video 3", "clipCount": 0, "clips": []},
                    ],
                    "audioTracks": [
                        {"index": 0, "name": "Audio 1", "clipCount": 0, "clips": []},
                        {"index": 1, "name": "Audio 2", "clipCount": 0, "clips": []},
                        {"index": 2, "name": "Audio 3", "clipCount": 0, "clips": []},
                    ],
                }
                self._send_json(200, {"status": "ok", "result": timeline_state})
                return

            # 2. Init Project
            if "argon_initProject" in full_code:
                self._send_json(200, {
                    "status": "ok",
                    "result": {
                        "status": "ok",
                        "action": "initProject",
                        "sequenceName": "Mock_Master_Timeline",
                        "projectPath": "C:/Mock/Project.prproj",
                    },
                })
                return

            # 3. Insert Clip
            if "argon_insertClip" in full_code:
                self._send_json(200, {
                    "status": "ok",
                    "result": {
                        "status": "ok",
                        "action": "insertClip",
                        "trackIndex": 0,
                        "clipIndex": 0,
                    },
                })
                return

            # 4. Motion / Transform
            if "argon_applyTransform" in full_code:
                self._send_json(200, {
                    "status": "ok",
                    "result": {
                        "status": "ok",
                        "action": "applyTransform",
                        "scale": 108.0,
                    },
                })
                return

            # 5. Audio Ducking & Gain
            if "argon_applyAudioGainAndDucking" in full_code:
                self._send_json(200, {
                    "status": "ok",
                    "result": {
                        "status": "ok",
                        "action": "applyAudioGainAndDucking",
                        "appliedDb": -22.0,
                    },
                })
                return

            # 6. After Effects Comp Generation
            if "argon_createCompWithText" in full_code:
                self._send_json(200, {
                    "status": "ok",
                    "result": {
                        "status": "ok",
                        "action": "createCompWithText",
                        "outputPath": "C:/Mock/VFX/Callout.mov",
                    },
                })
                return

            # 7. Photoshop Thumbnail
            if "argon_createThumbnail" in full_code:
                self._send_json(200, {
                    "status": "ok",
                    "result": {
                        "status": "ok",
                        "action": "createThumbnail",
                        "outputPath": "C:/Mock/Thumbnails/Thumb.psd",
                    },
                })
                return

            # Default successful execution
            self._send_json(200, {"status": "ok", "result": "mock_jsx_success"})
            return

        self._send_json(404, {"status": "error", "error": "Not Found"})


class MockAdobeCluster:
    """Manages mock servers across ports (8088, 8089, 8090) for testing."""

    def __init__(self, ports: Optional[List[int]] = None):
        self.ports = ports or [8088, 8089, 8090]
        self.servers: Dict[int, ThreadedHTTPServer] = {}
        self.threads: Dict[int, threading.Thread] = {}

    def start(self) -> None:
        """Start mock HTTP listeners on configured ports."""
        for port in self.ports:
            try:
                server = ThreadedHTTPServer(("127.0.0.1", port), MockAdobeRequestHandler)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                self.servers[port] = server
                self.threads[port] = thread
                logger.info(f"Mock Adobe Server listening on port {port}")
            except OSError as e:
                logger.warning(f"Port {port} already bound or unavailable: {e}")

        # Brief settle time
        time.sleep(0.05)

    def stop(self) -> None:
        """Shutdown all active mock server listeners."""
        for port, server in self.servers.items():
            try:
                server.shutdown()
                server.server_close()
            except Exception as e:
                logger.warning(f"Error shutting down mock server on port {port}: {e}")
        self.servers.clear()
        self.threads.clear()

    def __enter__(self) -> MockAdobeCluster:
        self.start()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.stop()


if __name__ == "__main__":
    cluster = MockAdobeCluster([8088, 8089, 8090])
    cluster.start()
    print("Mock Adobe CEP servers running on 8088, 8089, 8090. Press Ctrl+C to exit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        cluster.stop()
        print("Mock servers stopped.")
