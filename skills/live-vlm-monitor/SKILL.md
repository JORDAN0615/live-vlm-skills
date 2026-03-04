---
name: live-vlm-monitor
description: Real-time VLM video analysis. Start/stop monitoring RTSP or webcam streams, get AI analysis results, detect keywords like WARNING.
version: 1.0.0
metadata:
  openclaw:
    requires:
      bins: ["python3"]
      anyBins: ["live-vlm-webui", "python3"]
    emoji: "📹"
    homepage: "https://github.com/nvidia-ai-iot/live-vlm-webui"
---

# Live VLM Monitor

Monitor live video with Vision Language Models. Results are saved to `/tmp/vlm-results.jsonl`.

## Start RTSP Monitoring (headless, no browser needed)

Use exec tool with `background: true`:

```
command: python3 {baseDir}/scripts/start_rtsp.py \
  --rtsp-url <rtsp_url> \
  --model <model_name> \
  --api-base <api_base_url> \
  --prompt "<prompt_text>" \
  --frame-interval <N>
background: true
```

Save the returned `sessionId`. Monitoring runs until you call stop.

**Parameters:**
- `--rtsp-url` — Full RTSP URL (e.g. `rtsp://user:pass@192.168.1.100:554/stream`)
- `--model` — Model name (e.g. `llava:7b`, `llama-3.2-11b-vision-instruct`)
- `--api-base` — API base URL (e.g. `http://localhost:11434/v1` for Ollama)
- `--api-key` — API key (default: `EMPTY` for local servers)
- `--prompt` — Prompt for VLM analysis (default: describe the scene)
- `--frame-interval` — Process every Nth frame (default: 30)
- `--max-tokens` — Max tokens in response (default: 512)

## Start Webcam Monitoring (browser required)

Webcam access requires a browser. Run two background processes:

**Step 1** — Start the web server:
```
command: {baseDir}/scripts/start_webcam.sh --model <model> --api-base <api_base>
background: true
```
Save sessionId as `serverSessionId`.

**Step 2** — Start the WebSocket logger:
```
command: python3 {baseDir}/scripts/ws_to_file.py
background: true
```
Save sessionId as `wsSessionId`.

**Tell the user:** "Please open https://localhost:8090 in your browser and click the green START button to connect your webcam."

## Get Latest Results

Poll for new results periodically (e.g. every 30 seconds):

```
command: {baseDir}/scripts/get_results.sh --n 10 --since <last_timestamp>
```

**Returns:** JSON array of result objects, each with:
- `text` — VLM analysis text
- `timestamp` — Unix timestamp (float)
- `latency_ms` — Inference latency in milliseconds
- `frame_count` — Frame number when captured
- `mode` — `"rtsp"` or `"webcam"`

**IMPORTANT:** If any result's `text` starts with `"WARNING:"`, alert the user immediately with the full message.

## Check Monitoring Status

```
command: {baseDir}/scripts/get_results.sh --status
```

Returns JSON with:
- `running` — whether the monitor process is active
- `pid` — process ID (if running)
- `mode` — `"rtsp"` or `"webcam"`
- `total_results` — total inferences written
- `uptime_seconds` — seconds since first result
- `last_result` — most recent result object (or null)

## Stop Monitoring

Terminate the background process(es) first:
```
process: terminate <sessionId>
```

Then clean up:
```
command: {baseDir}/scripts/stop.sh
```

## Example: RTSP with WARNING detection

```
# Start monitoring a security camera
command: python3 {baseDir}/scripts/start_rtsp.py \
  --rtsp-url rtsp://admin:password@192.168.1.50/stream1 \
  --model llava:7b \
  --api-base http://localhost:11434/v1 \
  --prompt "Describe the scene. If you see a person, fire, or unusual activity, start your response with WARNING:" \
  --frame-interval 60
background: true
```

Then poll every 30 seconds:
```
command: {baseDir}/scripts/get_results.sh --n 5 --since 0
```

If any result contains `"WARNING:"`, send a Telegram notification with the full text.
