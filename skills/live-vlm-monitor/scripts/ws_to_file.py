#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
WebSocket logger for webcam mode.

Connects to live-vlm-webui's WebSocket endpoint and writes every
vlm_response message to /tmp/vlm-results.jsonl.

Run this after start_webcam.sh has started the server.

Usage:
    python3 ws_to_file.py [--url wss://localhost:8090/ws] [--results-file /tmp/vlm-results.jsonl]
"""

import argparse
import asyncio
import json
import logging
import signal
import ssl
import sys
import time
from pathlib import Path

try:
    import aiohttp
except ImportError:
    print(
        "[ws_to_file] ERROR: aiohttp not found. Install with: pip install aiohttp",
        flush=True,
    )
    sys.exit(1)

RESULTS_FILE = Path("/tmp/vlm-results.jsonl")
WS_PID_FILE = Path("/tmp/vlm-monitor-ws.pid")

logging.basicConfig(
    level=logging.WARNING,
    format="[ws_to_file] %(levelname)s: %(message)s",
)

_stopped = False


def _handle_signal(signum, frame):
    global _stopped
    _stopped = True
    print(f"\n[ws_to_file] Received signal {signum}, stopping...", flush=True)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Connect to live-vlm-webui WebSocket and log vlm_response to JSONL"
    )
    parser.add_argument(
        "--url",
        default="wss://localhost:8090/ws",
        help="WebSocket URL (default: wss://localhost:8090/ws)",
    )
    parser.add_argument(
        "--results-file",
        default=str(RESULTS_FILE),
        help=f"Output JSONL file (default: {RESULTS_FILE})",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=3.0,
        help="Seconds to wait before retrying on disconnect (default: 3)",
    )
    parser.add_argument(
        "--startup-wait",
        type=float,
        default=5.0,
        help="Seconds to wait for server startup before connecting (default: 5)",
    )
    return parser.parse_args()


async def connect_and_log(url: str, results_path: Path, retry_delay: float):
    """Connect to WebSocket and write vlm_response messages to file."""
    # Disable SSL verification for self-signed certificates (live-vlm-webui default)
    ssl_ctx = ssl.create_default_context()
    ssl_ctx.check_hostname = False
    ssl_ctx.verify_mode = ssl.CERT_NONE

    message_count = 0

    async with aiohttp.ClientSession() as session:
        try:
            async with session.ws_connect(url, ssl=ssl_ctx) as ws:
                print(f"[ws_to_file] Connected to {url}", flush=True)

                async for msg in ws:
                    if _stopped:
                        break

                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = json.loads(msg.data)
                        except json.JSONDecodeError:
                            continue

                        if data.get("type") != "vlm_response":
                            continue

                        text = data.get("text", "")
                        metrics = data.get("metrics", {})

                        entry = {
                            "text": text,
                            "timestamp": time.time(),
                            "latency_ms": round(metrics.get("last_latency_ms", 0), 1),
                            "inference_count": metrics.get("total_inferences", 0),
                            "mode": "webcam",
                        }

                        with open(results_path, "a") as f:
                            f.write(json.dumps(entry) + "\n")

                        message_count += 1
                        preview = text[:100] + "..." if len(text) > 100 else text
                        print(f"[ws_to_file] #{message_count}: {preview}", flush=True)

                        if text.upper().startswith("WARNING"):
                            print(f"[ws_to_file] *** WARNING DETECTED: {text}", flush=True)

                    elif msg.type in (aiohttp.WSMsgType.ERROR, aiohttp.WSMsgType.CLOSE):
                        print(f"[ws_to_file] WebSocket closed: {msg}", flush=True)
                        break

        except aiohttp.ClientConnectorError as e:
            print(f"[ws_to_file] Connection failed: {e}", flush=True)
            raise


async def main(args):
    import os

    global _stopped

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    results_path = Path(args.results_file)
    results_path.parent.mkdir(parents=True, exist_ok=True)

    WS_PID_FILE.write_text(str(os.getpid()))

    print(f"[ws_to_file] Waiting {args.startup_wait}s for server to start...", flush=True)
    await asyncio.sleep(args.startup_wait)

    while not _stopped:
        try:
            await connect_and_log(args.url, results_path, args.retry_delay)
        except Exception as e:
            if _stopped:
                break
            print(f"[ws_to_file] Disconnected ({e}), retrying in {args.retry_delay}s...", flush=True)
            await asyncio.sleep(args.retry_delay)

    WS_PID_FILE.unlink(missing_ok=True)
    print("[ws_to_file] Stopped.", flush=True)


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args))
