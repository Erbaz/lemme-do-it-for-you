# Lemme Do It For You — Self-Correcting Vision Agent

An RPA agent that moves the mouse cursor to GUI components by analyzing screenshots with a multimodal vision model. Uses iterative self-correction with spatial reasoning to converge on target element coordinates.

![License](https://img.shields.io/badge/License-MIT-green)

---

## Table of Contents

- [Features](#features)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [How It Works](#how-it-works)
- [Coordinate Convergence](#coordinate-convergence)
- [Key Concepts](#key-concepts)
- [API Reference](#api-reference)
- [Logging & Token Tracking](#logging--token-tracking)
- [Troubleshooting](#troubleshooting)

---

## Features

- **GUI Element Localization** — Move the mouse cursor to any visible GUI component (buttons, icons, form fields, menu items, etc.) by describing them in natural language
- **Visual Screen Analysis** — Get a detailed description of the current screen state (open windows, browser tabs, UI elements, disabled controls)
- **Crop-and-Zoom Convergence** — Phase 1 identifies a grid cell on the full screen; Phase 2 crops and zooms into that cell with a fresh 8×8 sub-grid for 64× finer precision; depth reduction backs out to search a different cell when the target isn't found
- **Dual-Gate Verification** — Two independent LLM checks (target in grid region + target at crosshair) must both pass before confirming a match
- **8×8 Grid Overlay** — Yellow grid with zero-indexed row/column labels (0-7) on every screenshot, anchoring spatial reasoning
- **Depth Reduction** — Auto-recovers from misidentified grid cells by returning to full-screen grid scan when the target isn't visible in the current crop
- **Human-Like Mouse Movement** — Smooth easing animation (ease-in-out quadratic) with randomized perturbations mimics natural human cursor movement
- **Resolution-Independent Coordinates** — All internal coordinates use a normalized 0–1000 scale, making the system resolution-agnostic
- **Crosshair History Tracking** — Every cursor position is recorded as a colored marker on screenshots, building a visual search history

---

## Project Structure

```
lemme-do-it-for-you/
├── agent/
│   ├── self_correcting_vision_agent.py    # V1/V2 — screen-wide crosshair (legacy)
│   ├── self_correcting_vision_agent_3.py  # V3 — local crosshair, cumulative map, spatial reasoning
│   ├── self_correcting_vision_agent_4.py  # V4 — crop-and-zoom iterative convergence with 8x8 grid
│   ├── tools.py                            # Tool interface (move_mouse, analyze_screen, click, type_text, etc.)
│   └── model.py                            # Loads .env config, sets up LLM (Ollama or OpenRouter)
├── constants/
│   └── allowed_hotkeys.py                  # Whitelisted keyboard hotkeys
├── test_vision_agent.py                    # Diagnostic test script
├── .env                                    # Model provider and configuration
└── README.md
```

---

## Quick Start

### Prerequisites

- Python 3.12+
- [Ollama](https://ollama.com/) running a vision-capable model (e.g., `qwen3-vl:4b-instruct`, `qwen3-vl:8b-instruct`)
- Or an OpenRouter API key

### 1. Configure Environment

```bash
cp .env.example .env
# Edit .env to set MODEL_PROVIDER, MODEL_NAME, etc.
```

| Variable             | Default                  | Description                |
| -------------------- | ------------------------ | -------------------------- |
| `MODEL_PROVIDER`     | `ollama`                 | `ollama` or `openrouter`   |
| `MODEL_NAME`         | `qwen3-vl:8b-instruct`   | Vision model name          |
| `OLLAMA_BASE_URL`    | `http://localhost:11434` | Ollama server URL          |
| `OPENROUTER_API_KEY` | _(empty)_                | OpenRouter API key         |
| `CONTEXT_WINDOW`     | `8192`                   | LLM context window size    |
| `REQUEST_TIMEOUT`    | `120.0`                  | Request timeout in seconds |

### 2. Run Interactively

```bash
python -m agent.self_correcting_vision_agent_4
```

### 3. Use Programmatically

```python
from agent.self_correcting_vision_agent_4 import SelfCorrectingVisionAgentV4

agent = SelfCorrectingVisionAgentV4(model_name="qwen3-vl:4b-instruct", verbose=True)

# Locate a GUI element and move the mouse to it
result = agent.locate_element(target="google chrome icon on taskbar")
print(f"Found at ({result.x}, {result.y}) with {result.confidence} confidence in {result.iterations} iterations")

# Analyze the current screen
analysis = agent.analyze_current_screen(prompt="What browser tabs are open?")
print(analysis)
```

### 4. Use via Tool Interface

```python
from agent.tools import move_mouse, analyze_screen, left_click, type_text, press_key, execute_hotkey

result = move_mouse(prompt="the save button in the toolbar")
description = analyze_screen(prompt="Describe all open windows")
left_click()
type_text("Hello, World!")
press_key("enter")
execute_hotkey(["ctrl", "s"])
```

### 5. Run Diagnostics

```bash
python test_vision_agent.py
```

## Configuration

### `SelfCorrectingVisionAgentV4` Parameters

```python
SelfCorrectingVisionAgentV4(
    model_name="qwen3-vl:4b-instruct",
    context_window=8192, request_timeout=300.0, max_image_size=1280,
    grid_divisions=8, overlap_percentage=0.10, verbose=True, cleanup_screenshots=True,
)
```

| Parameter | Default | Description |
|---|---|---|
| `grid_divisions` | `8` | Grid size (8 means 8×8 = 64 cells) |
| `overlap_percentage` | `0.10` | Overlap between grid cells (10%) for border element confidence |
| `max_image_size` | `1280` | Maximum width/height for LLM input images |

### `locate_element` Parameters

```python
result = agent.locate_element(target="chrome icon", max_iterations=5)
```

Returns a `LocateResult` dataclass with `target`, `x`, `y`, `confidence`, `iterations`, `screen_width`, `screen_height`.

---

## How It Works

### Overview

The **V4 agent** uses a **crop-and-zoom iterative convergence** loop to locate GUI elements. It combines a multimodal vision model (LLM with image input) with a normalized coordinate system (0–1000) and an 8×8 grid overlay. Each iteration narrows the search field by cropping and zooming into the region from the previous step, dramatically increasing precision.

### Crop-and-Zoom Workflow

```
PHASE 1: Full-Screen Grid Scan
  Capture full screenshot (scaled) with 8×8 grid overlay
  Ask LLM: "Which grid cell contains the target?"
  Response: {"grid_vector": "row x column"}  e.g., "5 x 4"
      |
      v
PHASE 2: Cropped Zoom-In
  Crop to the identified grid cell (with 10% overlap for border elements)
  Draw 8×8 sub-grid + red crosshair at cell center
  Ask LLM: "Which sub-cell contains the target?"
  Response: {"grid_vector": "3 x 2"}
  Convert sub-grid position back to full-screen normalized coords
      |
      v
VERIFICATION LOOP (up to max_iterations):
  1. MOVE: Normalized coords → native screen pixels (ease-in-out easing)
  2. CAPTURE: Two images:
     - CLEAN crop with grid overlay (no crosshair) → "Is target visible in this region?"
     - CROSSHAIR crop with grid + red crosshair → "Does crosshair sit on the target?"
  3. VERIFY: If target confirmed at crosshair position → SUCCESS!
  4. RE-ESTIMATE: 
     - If target NOT at crosshair: ask LLM to move to a different sub-cell
     - If target NOT in grid: trigger depth reduction (go back to full-screen grid)
  5. UPDATE: Push current position to history, continue loop
```

**Phase 1-N:** Normalized `(nx, ny)` coordinates are resolution-independent (0–1000 space). Screenshots are annotated with an 8×8 yellow grid (125px intervals), a local RED crosshair (25px ticks, 2px dot, 14px ring), and colored history markers from previous iterations. The LLM's crosshair and grid reasoning provides spatial context for each refinement step.

---

## Coordinate Convergence

### Normalized Coordinate Space (0-1000)

All coordinates use a **normalized 0-1000 space** independent of screen resolution:

- (0, 0) = top-left, (1000, 1000) = bottom-right, (500, 500) = center

**Conversion:** `nx = (x / screen_width) * 1000`

**Crop-relative remapping:** When the image is cropped to a sub-region and resized, full-screen normalized coordinates are remapped relative to the crop before drawing the crosshair: `pixel_x = ((nx - x_min) / crop_width) * image_width`. This ensures the crosshair appears at the correct position within the zoomed crop.

### Coordinate Convergence

The V4 agent converges through a **zoom hierarchy**:

```
Iteration 1: Phase 1 finds grid cell (5, 4) → Phase 2 zooms in → crosshair at (715, 812)
Iteration 2: Target not at crosshair → re-estimate to sub-cell (7, 2) → (659, 991)  
Iteration 3: Target confirmed at crosshair → native (1265, 1070), high confidence, 3 iterations
```

**Phase 1** gives ~8× precision (screen divided into 64 cells).  
**Phase 2** adds another 8× precision (each cell subdivided into 64 sub-cells).  
This gives **~64× effective resolution** over the original screen in just 2 LLM calls.

**Depth reduction** — If the target is not found in the current crop, the agent backs out to the full-screen grid and searches from a different cell. This prevents getting stuck in an area where the target doesn't exist.

---

## Key Concepts

### 1. 8×8 Grid Overlay with Crop-and-Zoom

The V4 agent overlays a yellow 8×8 grid (125px intervals in normalized 0-1000 space) on screenshots. Zero-indexed row/column labels (0-7) let the LLM identify grid cells precisely. After Phase 1 identifies a cell, the agent crops to that cell and draws a fresh 8×8 sub-grid, enabling 64× finer precision.

### 2. Dual-Gate Verification

```python
if target_in_grid is True and target_at_crosshair is True:
    return LocateResult(...)  # SUCCESS
```

Two separate LLM checks must both pass: the target must be visible in the grid region **and** the crosshair must be positioned directly on the target.

### 3. Local Crosshair Design

Local ticks instead of screen-wide lines: 25px ticks with 6px gap, 2px center dot, 14px target ring. Prevents visual contact with nearby UI elements.

### 4. History Tracking

Previous crosshair positions are recorded as colored markers (T1=cyan, T2=magenta, T3=green, T4=orange, T5=cyan2, T6=pink), each labeled with exact normalized coordinates. Provides spatial context for the LLM.

### 5. Depth Reduction

If the target is not visible in the current crop, the agent discards the crop and returns to the full-screen grid to search a different cell. This prevents infinite loops in regions where the target doesn't exist.

### 6. Human-Like Mouse Movement

```python
t = pytweening.easeInOutQuad(i / steps)
curr_x = (1-t)**2 * start_x + 2*(1-t)*t * mid_x + t**2 * target_x
```

Smooth Bezier-style easing with randomized perturbations mimics natural human cursor movement.

---

## API Reference

### `SelfCorrectingVisionAgentV4`

- `locate_element(target, max_iterations=5)` -> `LocateResult`
- `analyze_current_screen(prompt)` -> text description

### Tool Functions (`agent.tools`)

| Function                 | Description                             |
| ------------------------ | --------------------------------------- |
| `move_mouse(prompt)`     | Move cursor to target GUI element       |
| `analyze_screen(prompt)` | Describe current screen state           |
| `left_click()`           | Click at current cursor position        |
| `right_click()`          | Right-click at current cursor position  |
| `double_click()`         | Double-click at current cursor position |
| `type_text(text)`        | Type text with human-like delays        |
| `press_key(key)`         | Press a single key                      |
| `execute_hotkey(keys)`   | Execute keyboard hotkey combo           |

### `LocateResult`

Dataclass with `target`, `x`, `y`, `confidence`, `iterations`, `screen_width`, `screen_height`.

---

## Logging & Token Tracking

Every session of `SelfCorrectingVisionAgentV4` automatically creates a timestamped log file in the `.logs/` directory.

### Log File Naming

Each time `main.py` is run, a new log file is created named with the session start timestamp:

```
.logs/
└── 2025-09-25_14-30-00_agent.log
```

Log files are **never truncated** — they append to existing files.

### What Gets Logged

All log entries are prefixed with an ISO timestamp:

```
[2025-09-25 14:30:00] [INFO] Session started | Model: qwen3-vl:8b-instruct | Context Window: 262144 | Log file: 2025-09-25_14-30-00_agent.log
[2025-09-25 14:30:01] [DEBUG] Image: iter_0.png | Size: 124800 bytes | Format: PNG | Mode: RGB
[2025-09-25 14:30:05] [INFO] LLM Call #1 | Prompt tokens: 4521 | Completion tokens: 1832 | Cumulative total: 6353 | Context: 262144 | Remaining: 255791 | Usage: 2.42%
```

### Token Counting

The agent uses **LlamaIndex's `TokenCountingHandler`** to track every LLM interaction:

- **Prompt tokens** — tokens sent to the model (input)
- **Completion tokens** — tokens received from the model (output)
- **Cumulative total** — running sum of all tokens across the session

### Context Size & Token Length Incrementer

The `TokenIncrementer` tracks token consumption against the configured `context_window`:

| Metric | Description |
|---|---|
| `context_window` | Maximum tokens the model can process (from `.env`) |
| `cumulative_total` | Running total of all tokens used so far |
| `remaining_tokens` | Tokens left before hitting the limit |
| `percent_used` | Percentage of context window consumed |
| `percent_remaining` | Percentage of context window remaining |
| `call_count` | Total number of LLM calls made in the session |

Each LLM call increments the counter, so you can monitor how close the session is to exhausting the context window.

### Accessing Token Data Programmatically

```python
from agent.self_correcting_vision_agent_4 import SelfCorrectingVisionAgentV4
import agent.logger_setup as log_setup

agent = SelfCorrectingVisionAgentV4(verbose=True)
result = agent.locate_element(target="chrome icon")

# Get the token incrementer summary
inc = log_setup.get_token_incrementer()
print(f"Total tokens: {inc.cumulative_total}")
print(f"Context window: {inc.context_window}")
print(f"Remaining: {inc.remaining_tokens}")
print(f"Usage: {inc.percent_used}%")
print(f"Total LLM calls: {inc._call_count}")
```

### Log Level

- `DEBUG` — Image details, prompts sent, full LLM responses
- `INFO` — Session start/end, token summaries, LLM call summaries
- `STEP` — Iteration progress, coordinate updates
- `DONE` — Successful target confirmation
- `ERROR` — Failed JSON parsing, unexpected responses

---

## Troubleshooting

- **Module not found** - Run from project root directory
- **Model timeout** - Check Ollama/OpenRouter, increase `request_timeout`
- **False positives** - Set `cleanup_screenshots=False`, review `iter_*.png`
- **False negatives** - Be more specific, increase `max_iterations` to 8+
- **Crosshair misalignment** - Ensure `crop_region` coordinates are correctly mapped; review `.logs/` for coordinate log lines
- **Model not responding** - Check model is loaded and running, increase `request_timeout`

### Debugging

```python
agent = SelfCorrectingVisionAgentV4(cleanup_screenshots=False)
result = agent.locate_element(target="my target")
# iter_0.png through iter_N.png preserved in working directory
```

---

## License

MIT
