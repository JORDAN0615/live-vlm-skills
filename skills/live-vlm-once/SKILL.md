---
name: live-vlm-once
description: One-shot VLM webcam analysis. Opens the built-in laptop camera, warms up for 5s, captures one frame, sends it to a local VLM (Ollama/vLLM), and returns the AI response. The prompt is fully customizable — agents should craft it to match the user's intent.
version: 1.1.0
metadata:
  openclaw:
    requires:
      bins: ["python3", "ffmpeg"]
      anyBins: ["live-vlm-webui", "python3"]
    emoji: "📸"
    homepage: https://github.com/nvidia-ai-iot/live-vlm-webui
---

# Live VLM Once

Capture a single frame from your webcam and get instant VLM analysis.
The frame is automatically saved to `images/` as a PNG for reference.

## Quick Start

```bash
python3 {baseDir}/scripts/analyze.py \
  --model Qwen/Qwen3-VL-30B-A3B-Instruct \
  --api-base http://172.17.5.206:8000/v1
  --prompt "Describe what you see in one sentence."
```

## Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `--model` | Yes | - | VLM model name. Check available models with `ollama list`. |
| `--prompt` | No | "Describe what you see in this image in one sentence." | **Craft this to match the user's intent.** See prompt guide below. |
| `--camera` | No | auto-detect built-in | Camera index. **On this machine: `--camera 1` = MacBook Pro, `--camera 0` = iPhone.** Use `--list-cameras` to see options. |
| `--warmup` | No | `5.0` | Seconds to warm up camera before capture (auto-exposure stabilization). |
| `--disconnect` | No | `7.0` | Seconds after open to disconnect camera. Must be > `--warmup`. |
| `--api-base` | No | auto-detect | API base URL (`http://localhost:11434/v1` for Ollama, `http://localhost:8000/v1` for vLLM). |
| `--api-key` | No | `EMPTY` | API key. Use `EMPTY` for local servers. |
| `--max-tokens` | No | `512` | Max tokens in VLM response. |
| `--save-image` | No | - | Extra path to also save the captured frame. |
| `--list-cameras` | No | - | Print available cameras and exit. |
| `--loop` | No | off | Keep camera open and analyze repeatedly (Ctrl+C to stop). |
| `--interval` | No | `2.0` | Seconds between analyses in `--loop` mode. |

## Prompt Guide for Agents

The `--prompt` is the most important parameter to customize. Match it to what the user is actually asking:

| User intent | Suggested prompt |
|---|---|
| General description | `"Describe what you see in one sentence."` |
| Safety / security check | `"Start your response with SAFE or WARNING. Then describe what you see."` |
| Person detection | `"Is there a person visible? Answer YES or NO, then describe."` |
| Object identification | `"List the main objects you can see."` |
| Specific question | Pass the user's question directly as the prompt. |

## Camera Index Reference (this machine)

| `--camera` | Device | Notes |
|---|---|---|
| `1` | MacBook Pro built-in camera | Use this for laptop view |
| `0` | iPhone camera (Continuity Camera) | Use this for phone/mobile view |

Use `--list-cameras` to verify on other machines.

## Examples

### MacBook Pro camera — describe scene
```bash
python3 {baseDir}/scripts/analyze.py \
  --camera 1 \
  --model Qwen/Qwen3-VL-30B-A3B-Instruct \
  --api-base http://172.17.5.206:8000/v1 \
  --prompt "Describe what you see in detail."
```

### MacBook Pro camera — safety check
```bash
python3 {baseDir}/scripts/analyze.py \
  --camera 1 \
  --model Qwen/Qwen3-VL-30B-A3B-Instruct \
  --api-base http://172.17.5.206:8000/v1 \
  --prompt "Start your response with SAFE or WARNING. Is there any person, fire, or unusual activity?"
```

### MacBook Pro camera — continuous monitoring (every 10s)
```bash
python3 {baseDir}/scripts/analyze.py \
  --camera 1 \
  --model Qwen/Qwen3-VL-30B-A3B-Instruct \
  --api-base http://172.17.5.206:8000/v1 \
  --prompt "Is there anyone in the room? Answer YES or NO." \
  --loop --interval 10
```

### iPhone camera — describe scene
```bash
python3 {baseDir}/scripts/analyze.py \
  --camera 0 \
  --model Qwen/Qwen3-VL-30B-A3B-Instruct \
  --api-base http://172.17.5.206:8000/v1 \
  --prompt "Describe what you see in detail."
```

### List available cameras
```bash
python3 {baseDir}/scripts/analyze.py --list-cameras
```

## Output

```
[live-vlm-once] Using API: http://172.17.5.206:8000/v1
[live-vlm-once] Using camera index 0
[live-vlm-once] Warming up camera for 5s...
[live-vlm-once] Capturing frame at 5s...
[live-vlm-once] Camera disconnected at 7s.
[live-vlm-once] Frame saved to images/frame_20260304_102530_0.png
[live-vlm-once] Analyzing with llama3.2-vision:11b...
[live-vlm-once] Result (18500ms):
<VLM response text here>

[JSON_OUTPUT] <VLM response text here>
```

Parse the `[JSON_OUTPUT]` line to extract the result programmatically.
The captured frame is always saved to `{baseDir}/images/` as a PNG.

## Camera Timeline

```
0s       3s       5s
|-warmup-|--hold--|--disconnect
                     ↑ camera released here
            ↑ frame captured here
```

After disconnect, VLM analysis runs with the already-captured frame.
