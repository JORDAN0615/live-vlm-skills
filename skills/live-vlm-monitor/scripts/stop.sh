#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Stop all live-vlm-monitor processes and clean up.
# Call this after terminating the background session(s) with the OpenClaw agent.
#
# Usage:
#   stop.sh [--clear-results]
#
# Options:
#   --clear-results   Also delete /tmp/vlm-results.jsonl

CLEAR_RESULTS=false
PID_FILE="/tmp/vlm-monitor.pid"
WS_PID_FILE="/tmp/vlm-monitor-ws.pid"
RESULTS_FILE="/tmp/vlm-results.jsonl"

while [[ $# -gt 0 ]]; do
    case "$1" in
        --clear-results) CLEAR_RESULTS=true; shift ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

_kill_pid_file() {
    local pid_file="$1"
    local label="$2"
    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file" 2>/dev/null)
        if [ -n "$pid" ]; then
            if kill -0 "$pid" 2>/dev/null; then
                echo "[live-vlm-monitor] Sending SIGTERM to $label (PID $pid)"
                kill -TERM "$pid" 2>/dev/null || true
                # Wait up to 5 seconds for graceful shutdown
                local i
                for i in $(seq 1 5); do
                    sleep 1
                    if ! kill -0 "$pid" 2>/dev/null; then
                        echo "[live-vlm-monitor] $label (PID $pid) stopped."
                        break
                    fi
                done
                # Force kill if still running
                if kill -0 "$pid" 2>/dev/null; then
                    echo "[live-vlm-monitor] Force killing $label (PID $pid)"
                    kill -KILL "$pid" 2>/dev/null || true
                fi
            else
                echo "[live-vlm-monitor] $label (PID $pid) not running (stale PID file)"
            fi
        fi
        rm -f "$pid_file"
    else
        echo "[live-vlm-monitor] No PID file for $label"
    fi
}

_kill_pid_file "$PID_FILE" "rtsp-monitor"
_kill_pid_file "$WS_PID_FILE" "ws-logger"

if [ "$CLEAR_RESULTS" = true ]; then
    if [ -f "$RESULTS_FILE" ]; then
        rm -f "$RESULTS_FILE"
        echo "[live-vlm-monitor] Deleted $RESULTS_FILE"
    fi
else
    if [ -f "$RESULTS_FILE" ]; then
        count=$(wc -l < "$RESULTS_FILE" 2>/dev/null || echo 0)
        echo "[live-vlm-monitor] Results file preserved: $RESULTS_FILE ($count entries)"
        echo "[live-vlm-monitor] To delete: rm $RESULTS_FILE"
    fi
fi

echo "[live-vlm-monitor] Cleanup complete."
