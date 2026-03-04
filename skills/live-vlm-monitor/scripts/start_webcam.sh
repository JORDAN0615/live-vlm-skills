#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Start live-vlm-webui web server for webcam monitoring.
# The agent runs this with background:true, then starts ws_to_file.py separately.
#
# Usage:
#   start_webcam.sh [--model <model>] [--api-base <url>] [--api-key <key>]
#                   [--prompt <prompt>] [--port <port>] [--process-every <N>]

set -euo pipefail

MODEL=""
API_BASE=""
API_KEY=""
PROMPT=""
PORT="8090"
PROCESS_EVERY="30"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --model)       MODEL="$2";        shift 2 ;;
        --api-base)    API_BASE="$2";     shift 2 ;;
        --api-key)     API_KEY="$2";      shift 2 ;;
        --prompt)      PROMPT="$2";       shift 2 ;;
        --port)        PORT="$2";         shift 2 ;;
        --process-every) PROCESS_EVERY="$2"; shift 2 ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

# Build live-vlm-webui command
CMD="live-vlm-webui"
CMD+=" --port $PORT"
CMD+=" --process-every $PROCESS_EVERY"

[[ -n "$MODEL" ]]     && CMD+=" --model $MODEL"
[[ -n "$API_BASE" ]]  && CMD+=" --api-base $API_BASE"
[[ -n "$API_KEY" ]]   && CMD+=" --api-key $API_KEY"
[[ -n "$PROMPT" ]]    && CMD+=" --prompt '$PROMPT'"

echo "[live-vlm-monitor] Starting webcam server on port $PORT"
echo "[live-vlm-monitor] Command: $CMD"
echo "[live-vlm-monitor] Open https://localhost:$PORT in browser and click START"

exec $CMD
