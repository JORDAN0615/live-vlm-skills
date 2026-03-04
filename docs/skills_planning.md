# Live VLM → Claude Code Skill 移植規劃

## 目標
把 live-vlm-webui 的核心 VLM 推理能力做成 Claude Code skill，讓使用者可以透過自然語言（包含手機 Telegram）觸發相機分析。

---

## 核心資料流（與網頁版相同，但去掉 WebRTC）

```
相機 (cv2.VideoCapture)
    ↓ 每 N 幀取一張
PIL Image → base64(JPEG)
    ↓
VLMService.analyze_image()
    → OpenAI-compatible API (Ollama / vLLM)
    → response text
    ↓
結果處理（直接回傳 / 閾值過濾 / Telegram 推送）
```

---

## 為何不用 WebRTC

WebRTC 需要瀏覽器作為相機存取層 (`getUserMedia`)。
Skill 場景下，相機在同一台機器，直接用 OpenCV 即可，整個 aiohttp + aiortc 層全部移除。

---

## 可移植的核心元件

| 元件 | 來源 | 備註 |
|---|---|---|
| `VLMService` | `vlm_service.py` | 幾乎原封不動可用 |
| 幀取樣邏輯 | `VideoProcessorTrack.recv()` | 改寫成 OpenCV loop |
| 防重疊鎖 `_processing_lock` | `VLMService` | 直接沿用 |
| 幀延遲丟棄 | `VideoProcessorTrack` | 可選保留 |
| 後端自動偵測 | `detect_local_service_and_model()` | 直接沿用 |
| 熱更換 prompt/model | `update_prompt()`, `update_api_settings()` | 直接沿用 |

## 不需要移植的元件

- WebRTC SDP 握手 (`offer()`)
- WebSocket server (`websocket_handler()`, `broadcast_*()`)
- aiohttp HTTP server
- GPU monitor UI loop
- index.html 前端

---

## Skill 設計：兩種模式

### 模式一：One-shot（拍一張分析）
```
User: "幫我看一下現在有沒有危險"
→ cv2.VideoCapture(0) 開相機
→ 取 1 張截圖
→ VLM 分析
→ 關相機
→ 回傳結果給 Claude
```
適合：即時問答、場景描述

### 模式二：Background Watchdog（持續監控）
```
User: "開始監控，有危險才通知我"
→ 啟動背景 process (寫 PID 到 /tmp/live_vlm.pid)
→ 立刻回傳 "監控已啟動"

[背景持續執行]
每 N 幀 → VLM →
  無危險 → 不動作
  有危險 → Telegram Bot 直接推送手機
```
適合：安全監控、異常偵測

---

## 持續回應處理策略

| 策略 | 適合場景 |
|---|---|
| 閾值過濾（只有危險才通知） | 安全監控、異常偵測 |
| 狀態變化才通知（前後不同） | 偵測人進出、物品移動 |
| 每 N 秒彙整摘要 | 環境描述、場景變化 |
| 全部回傳 | Debug、即時分析 |

---

## 建議的 Skill 檔案結構

```
skills/
├── live_vlm_once.sh      # Phase 1：One-shot 拍一張分析
├── live_vlm_start.sh     # Phase 2：啟動背景監控
├── live_vlm_stop.sh      # Phase 2：停止背景監控
└── live_vlm_daemon.py    # 背景監控核心邏輯
        ├── cv2.VideoCapture(0) 或 RTSP URL
        ├── 每 N 幀 → VLMService.analyze_image()
        ├── 結果寫入 /tmp/live_vlm_log.jsonl
        └── 觸發條件 → Telegram Bot API 推送
```

---

## 實作優先順序

```
Phase 1: live_vlm_once
  → 最簡單，拍一張 → VLM → 回 Claude，先跑通整條流程

Phase 2: live_vlm_daemon
  → background loop + 結果寫 log + PID 管理

Phase 3: Telegram 通知
  → 閾值觸發時直接推手機（不依賴 Claude）

Phase 4: RTSP 支援
  → 把 cv2.VideoCapture(0) 換成 RTSP URL，接獨立 IP camera
```

---

## 相機來源決策

| 場景 | 方案 |
|---|---|
| 筆電本機相機（Phase 1-3） | `cv2.VideoCapture(0)` |
| 獨立 IP camera（Phase 4） | RTSP URL（`rtsp_track.py` 可參考） |
| 手機相機 → 筆電 | 技術困難，暫不考慮 |

---

## 手機 Telegram 整合

使用者透過手機 Telegram 傳訊息給筆電上的 Claude Code。
Claude Code 收到後執行 skill，skill 透過 Telegram Bot API 直接推送結果給手機。
這條路**不需要**瀏覽器，也不需要 WebRTC。
