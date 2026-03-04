#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Read latest VLM results from /tmp/vlm-results.jsonl
#
# Usage:
#   get_results.sh [--n 10] [--since <timestamp>] [--status]
#
# Options:
#   --n <N>              Return the last N results (default: 10)
#   --since <timestamp>  Only return results after this Unix timestamp (default: 0)
#   --status             Print monitoring status summary and exit
#
# Output: JSON array of result objects (or status JSON for --status)

N=10
SINCE=0
STATUS=false
RESULTS_FILE="/tmp/vlm-results.jsonl"
PID_FILE="/tmp/vlm-monitor.pid"
WS_PID_FILE="/tmp/vlm-monitor-ws.pid"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --n)      N="$2";     shift 2 ;;
        --since)  SINCE="$2"; shift 2 ;;
        --status) STATUS=true; shift ;;
        *)
            echo '{"error": "Unknown argument: '"$1"'"}' >&2
            exit 1
            ;;
    esac
done

if [ "$STATUS" = true ]; then
    # Status report
    python3 - <<EOF
import json, os, time
from pathlib import Path

pid_file = Path("$PID_FILE")
ws_pid_file = Path("$WS_PID_FILE")
results_file = Path("$RESULTS_FILE")

# Check if main monitor process is running
running = False
pid = None
mode = "unknown"

if pid_file.exists():
    try:
        pid = int(pid_file.read_text().strip())
        os.kill(pid, 0)  # Signal 0 = existence check only
        running = True
        mode = "rtsp"
    except (ProcessLookupError, PermissionError, ValueError):
        running = False
        pid = None

if not running and ws_pid_file.exists():
    try:
        ws_pid = int(ws_pid_file.read_text().strip())
        os.kill(ws_pid, 0)
        running = True
        mode = "webcam"
        pid = ws_pid
    except (ProcessLookupError, PermissionError, ValueError):
        pass

# Read results for stats
total_results = 0
first_ts = None
last_result = None

if results_file.exists():
    with open(results_file) as f:
        for line in f:
            try:
                r = json.loads(line)
                total_results += 1
                if first_ts is None:
                    first_ts = r.get("timestamp", 0)
                last_result = r
            except Exception:
                pass

uptime = None
if first_ts is not None:
    uptime = round(time.time() - first_ts, 1)

print(json.dumps({
    "running": running,
    "pid": pid,
    "mode": mode if running else None,
    "total_results": total_results,
    "uptime_seconds": uptime,
    "last_result": last_result,
}, indent=2))
EOF
    exit 0
fi

# Results query
if [ ! -f "$RESULTS_FILE" ]; then
    echo '{"error": "No results file found. Is monitoring running?"}'
    exit 1
fi

python3 - <<EOF
import json, sys
from pathlib import Path

results_file = Path("$RESULTS_FILE")
since = float("$SINCE")
n = int("$N")

results = []
with open(results_file) as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            if r.get("timestamp", 0) > since:
                results.append(r)
        except json.JSONDecodeError:
            pass

print(json.dumps(results[-n:], indent=2))
EOF
