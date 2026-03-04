#!/usr/bin/env python3
"""
One-shot VLM analysis using local webcam.

Takes a single snapshot from the camera, sends it to VLM for analysis,
and prints the result. No background process needed.

Usage:
    python3 analyze.py --model llava:7b --prompt "Describe this image"
    python3 analyze.py --model llama-3.2-11b-vision-instruct \
        --api-base http://localhost:8000/v1 \
        --prompt "Is there any danger in this scene?"
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# Suppress verbose logs from dependencies
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("live_vlm_webui.vlm_service").setLevel(logging.WARNING)

import cv2
from PIL import Image

# live_vlm_webui must be installed (pip install live-vlm-webui or pip install -e .)
try:
    from live_vlm_webui.vlm_service import VLMService
except ImportError:
    print(
        "[live-vlm-once] ERROR: live_vlm_webui not found. "
        "Install with: pip install live-vlm-webui",
        flush=True,
    )
    sys.exit(1)


def list_cameras():
    """List available cameras using FFmpeg AVFoundation (accurate index mapping)."""
    import subprocess, re
    print("Available cameras (use --camera INDEX):", flush=True)

    # FFmpeg gives the definitive AVFoundation device list with correct indices
    try:
        result = subprocess.run(
            ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            capture_output=True, text=True, timeout=5
        )
        output = result.stderr
        in_video = False
        for line in output.splitlines():
            if "AVFoundation video devices" in line:
                in_video = True
                continue
            if "AVFoundation audio devices" in line:
                break
            if in_video:
                m = re.search(r"\[(\d+)\] (.+)", line)
                if m:
                    idx, name = m.group(1), m.group(2).strip()
                    # Check if OpenCV can open it
                    cap = cv2.VideoCapture(int(idx))
                    if cap.isOpened():
                        w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        cap.release()
                        print(f"  --camera {idx}  →  {name} ({w}x{h})", flush=True)
                    else:
                        print(f"  --camera {idx}  →  {name} (not accessible by OpenCV)", flush=True)
    except FileNotFoundError:
        # ffmpeg not available, fallback to index scan
        for i in range(5):
            cap = cv2.VideoCapture(i)
            if cap.isOpened():
                w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                print(f"  --camera {i}  →  Camera {i} ({w}x{h})", flush=True)
                cap.release()
    sys.exit(0)


def find_builtin_camera() -> int:
    """Use FFmpeg to find the built-in (non-iPhone) camera index."""
    import subprocess, re
    try:
        result = subprocess.run(
            ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            capture_output=True, text=True, timeout=5
        )
        in_video = False
        for line in result.stderr.splitlines():
            if "AVFoundation video devices" in line:
                in_video = True
                continue
            if "AVFoundation audio devices" in line:
                break
            if in_video:
                m = re.search(r"\[(\d+)\] (.+)", line)
                if m:
                    idx, name = int(m.group(1)), m.group(2).strip()
                    # Skip iPhone, desk view, and screen capture
                    skip_keywords = ["iPhone", "桌上", "Capture screen"]
                    if not any(k in name for k in skip_keywords):
                        return idx
    except Exception:
        pass
    return 0  # fallback


def parse_args():
    parser = argparse.ArgumentParser(description="One-shot VLM webcam analysis")
    parser.add_argument(
        "--list-cameras",
        action="store_true",
        help="List available cameras and exit",
    )
    parser.add_argument(
        "--camera",
        "-c",
        type=int,
        default=None,
        help="Camera index. Default: auto-detect built-in camera. Use --list-cameras to see all cameras.",
    )
    parser.add_argument(
        "--warmup",
        type=float,
        default=3.0,
        help="Seconds before capturing frame (default: 5.0)",
    )
    parser.add_argument(
        "--disconnect",
        type=float,
        default=5.0,
        help="Seconds after camera open to disconnect (default: 7.0)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="VLM model name (e.g. llava:7b, llama-3.2-11b-vision-instruct)",
    )
    parser.add_argument(
        "--api-base",
        default=None,
        help="VLM API base URL (auto-detected if not provided)",
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
        "--max-tokens",
        type=int,
        default=512,
        help="Maximum tokens in VLM response (default: 512)",
    )
    parser.add_argument(
        "--save-image",
        default=None,
        help="Optional: Save captured image to this path",
    )
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Keep camera open and analyze continuously (Ctrl+C to stop)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=2.0,
        help="Seconds between analyses in --loop mode (default: 2.0)",
    )
    return parser.parse_args()


def detect_api_base() -> str:
    """Auto-detect available VLM service."""
    import socket

    # Check Ollama (port 11434)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    if sock.connect_ex(("localhost", 11434)) == 0:
        sock.close()
        return "http://localhost:11434/v1"
    sock.close()

    # Check vLLM/SGLang (port 8000)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    if sock.connect_ex(("localhost", 8000)) == 0:
        sock.close()
        return "http://localhost:8000/v1"
    sock.close()

    # Default to Ollama
    return "http://localhost:11434/v1"


async def main(args):
    if args.list_cameras:
        list_cameras()

    if not args.model:
        print("[live-vlm-once] ERROR: --model is required. Use --list-cameras to see cameras.", flush=True)
        sys.exit(1)

    # Auto-detect API base if not provided
    api_base = args.api_base or detect_api_base()
    print(f"[live-vlm-once] Using API: {api_base}", flush=True)

    # Auto-detect built-in camera if not specified
    camera_index = args.camera if args.camera is not None else find_builtin_camera()
    print(f"[live-vlm-once] Using camera index {camera_index}", flush=True)

    # Initialize VLM service (shared for all captures)
    vlm_service = VLMService(
        model=args.model,
        api_base=api_base,
        api_key=args.api_key or "EMPTY",
        prompt=args.prompt,
        max_tokens=args.max_tokens,
    )

    # Open camera
    cap = cv2.VideoCapture(camera_index, cv2.CAP_AVFOUNDATION)
    if not cap.isOpened():
        print(f"[live-vlm-once] ERROR: Cannot open camera {camera_index}", flush=True)
        sys.exit(1)

    # Warm up: read frames for --warmup seconds so auto-exposure stabilizes
    camera_open_time = time.time()
    print(f"[live-vlm-once] Warming up camera for {args.warmup:.0f}s...", flush=True)
    warmup_end = camera_open_time + args.warmup
    while time.time() < warmup_end:
        cap.read()

    # Capture frame at warmup mark
    print(f"[live-vlm-once] Capturing frame at {args.warmup:.0f}s...", flush=True)
    ret, frame = cap.read()
    if not ret:
        print("[live-vlm-once] ERROR: Failed to capture frame", flush=True)
        sys.exit(1)

    # Hold camera open until --disconnect seconds, then release
    disconnect_at = camera_open_time + args.disconnect
    remaining = disconnect_at - time.time()
    if remaining > 0:
        print(f"[live-vlm-once] Holding camera for {remaining:.1f}s more...", flush=True)
        while time.time() < disconnect_at:
            cap.read()

    cap.release()
    print(f"[live-vlm-once] Camera disconnected at {args.disconnect:.0f}s.", flush=True)

    # Auto-save directory (relative to this script)
    images_dir = Path(__file__).parent.parent / "images"
    images_dir.mkdir(exist_ok=True)

    async def capture_and_analyze(index: int = 0) -> str:
        """Analyze a pre-captured frame."""
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(frame_rgb)

        # Always save to images/
        ts = time.strftime("%Y%m%d_%H%M%S")
        auto_save = images_dir / f"frame_{ts}_{index}.png"
        pil_image.save(auto_save)
        print(f"[live-vlm-once] Frame saved to {auto_save}", flush=True)

        if args.save_image:
            p = Path(args.save_image)
            save_path = str(p) if index == 0 else f"{p.stem}_{index}{p.suffix}"
            pil_image.save(save_path)
            print(f"[live-vlm-once] Image saved to {save_path}", flush=True)

        print(f"[live-vlm-once] Analyzing with {args.model}...", flush=True)
        start_time = time.perf_counter()

        result = ""
        for attempt in range(3):
            try:
                result = await vlm_service.analyze_image(pil_image)
                if result and not result.startswith("Error:"):
                    break
                print(f"[live-vlm-once] Empty/error response, retrying ({attempt+1}/3)...", flush=True)
            except Exception as e:
                print(f"[live-vlm-once] ERROR: VLM analysis failed: {e}", flush=True)
                if attempt == 2:
                    return ""

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        print(f"[live-vlm-once] Result ({elapsed_ms:.0f}ms):", flush=True)
        print(result, flush=True)
        print(f"\n[JSON_OUTPUT] {result}", flush=True)
        return result

    if args.loop:
        # Continuous mode: keep camera open, analyze every --interval seconds
        print(f"[live-vlm-once] Loop mode ON — interval: {args.interval}s | Ctrl+C to stop", flush=True)
        count = 0
        try:
            while True:
                await capture_and_analyze(count)
                count += 1
                await asyncio.sleep(args.interval)
        except KeyboardInterrupt:
            print(f"\n[live-vlm-once] Stopped after {count} analyses.", flush=True)
    else:
        # One-shot mode
        await capture_and_analyze()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(main(args))
