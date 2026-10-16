# Project Argon-Edit: Autonomous Multi-Agent Adobe Video Production Engine

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Adobe CEP 11/12](https://img.shields.io/badge/Adobe%20CEP-11%2F12-red.svg)](https://developer.adobe.com/)
[![Nvidia NIM](https://img.shields.io/badge/Nvidia%20NIM-Nemotron%20%7C%20Llama%203.2-green.svg)](https://build.nvidia.com)
[![FastMCP](https://img.shields.io/badge/MCP-FastMCP%20Ready-purple.svg)](https://github.com/modelcontextprotocol)

**Project Argon-Edit** is a production-grade, autonomous video editing system that connects Nvidia NIM reasoning models (`nvidia/llama-3.1-nemotron-70b-instruct`, `meta/llama-3.2-90b-vision-instruct`), Faster-Whisper, and persistent vector memory to the Adobe Creative Cloud suite (Premiere Pro, After Effects, Photoshop, Audition) via a live CEP HTTP bridge.

---

## 5 Hard Technical Laws Implemented

1. **The ES3 ExtendScript Law:** All Adobe ExtendScript (`.jsx`) strictly adheres to ECMAScript 3 (1999). No `const`, `let`, arrow functions, template literals, or modern array methods. Injects `json2.jsx` polyfill for JSON parsing.
2. **The Premiere Ticks Law:** Timeline positions and cuts are calculated in exact Premiere ticks:
   $$\text{1 Second} = 254\,016\,000\,000 \text{ Ticks}$$
3. **The Live CEP Socket Bridge Law:** Real-time bi-directional control via a Node.js-enabled Adobe CEP Extension listening on:
   - `localhost:8088` (Premiere Pro)
   - `localhost:8089` (After Effects)
   - `localhost:8090` (Photoshop)
4. **The Proxy Analysis Law:** Never sends raw 4K/8K camera footage to vision or audio APIs. Automatically extracts a 16kHz mono `.wav` and 480p proxy `.mp4` using `ffmpeg`, then maps all cuts back to master media in Premiere Pro.
5. **Zero Stubs / Zero Placeholders:** 100% functional Python and ExtendScript modules with comprehensive error handling, auto-debugging, and unit tests.

---

## Architecture Overview

```
argon_video_engine/
├── .env.example                      # Environment variables template
├── pyproject.toml                    # Python package specification
├── config/
│   ├── settings.py                   # Pydantic settings & Tick constants
│   └── editing_blueprints.json       # Pacing profiles (Retention, Cinematic, Documentary, Shortform)
├── adobe_cep_bridge/                 # Adobe CEP extension package
│   ├── CSXS/manifest.xml             # CEP 11/12 manifest targeting PPRO, AEFT, PHXS, AUDT
│   ├── .debug                        # CEP remote debugging configuration
│   ├── index.html                    # Panel web view and status dashboard
│   ├── js/CSInterface.js             # Adobe CEP JS API wrapper
│   ├── js/bridge_server.js           # Internal Node.js HTTP server executing evalScript()
│   ├── jsx/json2.jsx                 # Strict ES3 JSON polyfill
│   ├── jsx/premiere_core.jsx         # ES3 DOM & QE DOM operations for Premiere Pro
│   ├── jsx/aftereffects_core.jsx     # ES3 DOM operations for After Effects comps & MOGRTs
│   ├── jsx/photoshop_core.jsx        # ES3 DOM operations for YouTube thumbnail generation
│   └── install_bridge.py             # Automatic Windows Registry / macOS Plist & symlink installer
├── mcp_server/
│   ├── server.py                     # FastMCP Model Context Protocol server exposing Adobe tools
│   └── jsx_compiler.py               # ES3 AST validator and batch transaction compiler
├── memory/
│   ├── state_db.py                   # SQLite transactional state, action tracking, undo snapshots
│   └── style_memory.py               # ChromaDB vector store for user editing styles & LUT preferences
├── agents/
│   ├── schemas.py                    # Strict Pydantic v2 data contracts
│   ├── base_agent.py                 # Async Nvidia NIM client with exponential backoff & fallback
│   ├── ingestion_agent.py            # FFmpeg proxies, Faster-Whisper, PySceneDetect, RMS audio
│   ├── vision_agent.py               # Batched keyframe analysis via Llama-3.2-90B-Vision
│   ├── director_agent.py             # Hollywood Director Editor powered by Nemotron-70B
│   ├── vfx_motion_agent.py           # Kinetic text, lower-thirds, ProRes 4444 with Alpha renders
│   └── audio_master_agent.py         # -14 LUFS loudness, ducking envelopes, SFX, J/L cuts
├── tests/                            # Comprehensive unit & integration test suite (51 tests + Mock Adobe Server)
└── main_orchestrator.py              # Self-healing execution loop, CLI, and pipeline entry point
```

---

## Quickstart Guide

### 1. Installation

```bash
cd argon_video_engine
pip install -e .
```

### 2. Configure Environment

Copy `.env.example` to `.env` and set your Nvidia NIM API key:

```bash
cp .env.example .env
```

Edit `.env`:
```env
NVIDIA_API_KEY=nvapi-your-key-here
```

### 3. Install Adobe CEP Bridge

Run the automated installer to set `PlayerDebugMode=1` in the Windows Registry or macOS Plist and symlink the extension:

```bash
python adobe_cep_bridge/install_bridge.py
```

Check status:
```bash
python adobe_cep_bridge/install_bridge.py --check
```

### 4. Launch the Bridge in Adobe Apps

1. Open Adobe Premiere Pro (or After Effects / Photoshop).
2. Go to **Window** -> **Extensions** -> **Argon Video Engine Bridge**.
3. The panel will display an online status indicator listening on `http://127.0.0.1:8088`.

### 5. Run the Autonomous Video Pipeline

Process a folder of footage and assemble an automated edit in Premiere Pro:

```bash
python main_orchestrator.py pipeline "C:/path/to/raw_footage" --style Retention
```

Available pacing styles:
- `Retention`: Aggressive pacing, 0.25s dead-air elimination, 108% punch-ins, -22dB ducking.
- `Cinematic`: 0.6s breath pacing, cross dissolves, -18dB ducking, J-cut audio leads.
- `Documentary`: Investigative pacing, lower-thirds, archival B-roll cutaways.
- `Shortform`: Vertical 9:16 layout (1080x1920), kinetic subtitles, high-contrast zooms.

### 6. Run as an MCP Server

Argon-Edit exposes Model Context Protocol tools for AI assistants:

```bash
python mcp_server/server.py
```

Available MCP Tools:
- `inspect_live_premiere_timeline`: Real-time timeline inspection.
- `ingest_and_analyze_footage`: Multi-modal audio and vision ingestion.
- `generate_master_edit_plan`: Hollywood Director Nemotron edit planning.
- `execute_edit_plan_in_premiere`: Self-healing timeline execution.
- `create_after_effects_vfx_comp`: Kinetic motion graphics overlays.
- `generate_photoshop_thumbnail`: High-CTR YouTube thumbnail generator.
- `save_editing_rule_to_memory`: Persistent vector style memory.

---

## Running Tests

Run the full unit test suite:

```bash
python -m unittest discover tests
```
