#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
RTSP headless VLM monitoring.

Connects to an RTSP camera, runs VLM analysis every N frames,
and writes results to /tmp/vlm-results.jsonl.

Usage:
    python3 start_rtsp.py --rtsp-url rtsp://... --model llava:7b
    python3 start_rtsp.py --rtsp-url rtsp://... --model llava:7b \\
        --api-base http://localhost:11434/v1 \\
        --prompt "Describe the scene. Start with WARNING: if you see danger." \\
        --frame-interval 60
"""

import argparse
import asyncio
import json
import logging
import os
import signal
import sys
import time
from pathlib import Path

import cv2
from PIL import Image

# live_vlm_webui must be installed (pip install live-vlm-webui or pip install -e .)
try:
    from live_vlm_webui.rtsp_track import RTSPVideoTrack
    from live_vlm_webui.vlm_service import VLMService
except ImportError:
    print(
        "[live-vlm-monitor] ERROR: live_vlm_webui not found. "
        "Install with: pip install live-vlm-webui",
        flush=True,
    )
    sys.exit(1)

RESULTS_FILE = Path("/tmp/vlm-results.jsonl")
PID_FILE = Path("/tmp/vlm-monitor.pid")

logging.basicConfig(
    level=logging.WARNING,
    format="[live-vlm-monitor] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
_stopped = False


def _handle_signal(signum, frame):
    global _stopped
    _stopped = True
    print(f"\n[live-vlm-monitor] Received signal {signum}, stopping...", flush=True)


def parse_args():
    parser = argparse.ArgumentParser(
        description="RTSP headless VLM monitor — writes results to /tmp/vlm-results.jsonl"
    )
    parser.add_argument("--rtsp-url", required=True, help="RTSP stream URL")
    parser.add_argument("--model", required=True, help="VLM model name (e.g. llava:7b)")
    parser.add_argument(
        "--api-base",
        default="http://localhost:11434/v1",
        help="VLM API base URL (default: http://localhost:11434/v1)",
    )
    parser.add_argument(
        "--api-key",
        default="EMPTY",
        help="VLM API key (default: EMPTY for local servers)",
    )
    parser.add_argument(
        "--prompt",
        default="Describe what you see in this image in one sentence.",
        help="Prompt for VLM analysis",
    )
    parser.add_argument(
        "--frame-interval",
        type=int,
        default=30,
        help="Process every Nth frame (default: 30)",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=512,
        help="Maximum tokens in VLM response (default: 512)",
    )
    parser.add_argument(
        "--results-file",
        default=str(RESULTS_FILE),
        help=f"Path to results JSONL file (default: {RESULTS_FILE})",
    )
    return parser.parse_args()


async def main(args):
    global _stopped

    results_path = Path(args.results_file)
    results_path.parent.mkdir(parents=True, exist_ok=True)
    pid_file = PID_FILE

    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    # Write PID file
    pid_file.write_text(str(os.getpid()))
    print(f"[live-vlm-monitor] PID {os.getpid()} written to {pid_file}", flush=True)

    # Connect to RTSP stream in executor (blocking operation)
    print(f"[live-vlm-monitor] Connecting to RTSP: {args.rtsp_url}", flush=True)
    loop = asyncio.get_event_loop()
    try:
        rtsp_track = await loop.run_in_executor(
            None, lambda: RTSPVideoTrack(args.rtsp_url)
        )
    except Exception as e:
        print(f"[live-vlm-monitor] ERROR: Failed to connect to RTSP stream: {e}", flush=True)
        pid_file.unlink(missing_ok=True)
        sys.exit(1)

    # Initialize VLM service
    vlm_service = VLMService(
        model=args.model,
        api_base=args.api_base,
        api_key=args.api_key or "EMPTY",
        prompt=args.prompt,
        max_tokens=args.max_tokens,
    )

    frame_count = 0
    inference_count = 0
    print(
        f"[live-vlm-monitor] Started. Model={args.model}, interval={args.frame_interval} frames",
        flush=True,
    )
    print(f"[live-vlm-monitor] Writing results to {results_path}", flush=True)

    try:
        while not _stopped:
            try:
                frame = await rtsp_track.recv()
            except StopAsyncIteration:
                print("[live-vlm-monitor] RTSP stream ended.", flush=True)
                break
            except Exception as e:
                print(f"[live-vlm-monitor] Frame receive error: {e}", flush=True)
                if _stopped:
                    break
                await asyncio.sleep(1)
                continue

            frame_count += 1

            # Skip frames not on the interval
            if frame_count % args.frame_interval != 0:
                continue

            # Convert VideoFrame → PIL Image
            try:
                img_bgr = frame.to_ndarray(format="bgr24")
                img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(img_rgb)
            except Exception as e:
                print(f"[live-vlm-monitor] Frame conversion error: {e}", flush=True)
                continue

            # Run VLM inference (awaited directly — one at a time)
            try:
                text = await vlm_service.analyze_image(pil_img)
                metrics = vlm_service.get_metrics()
                inference_count += 1
            except Exception as e:
                print(f"[live-vlm-monitor] VLM error: {e}", flush=True)
                continue

            entry = {
                "text": text,
                "timestamp": time.time(),
                "latency_ms": round(metrics["last_latency_ms"], 1),
                "frame_count": frame_count,
                "inference_count": inference_count,
                "mode": "rtsp",
            }

            with open(results_path, "a") as f:
                f.write(json.dumps(entry) + "\n")

            preview = text[:100] + "..." if len(text) > 100 else text
            print(
                f"[live-vlm-monitor] #{inference_count} frame={frame_count} "
                f"({metrics['last_latency_ms']:.0f}ms): {preview}",
                flush=True,
            )

            # Warn loudly on WARNING prefix
            if text.upper().startswith("WARNING"):
                print(f"[live-vlm-monitor] *** WARNING DETECTED: {text}", flush=True)

    finally:
        rtsp_track.stop()
        pid_file.unlink(missing_ok=True)
        print(
            f"[live-vlm-monitor] Stopped. Total frames={frame_count}, inferences={inference_count}",
            flush=True,
        )


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args))
