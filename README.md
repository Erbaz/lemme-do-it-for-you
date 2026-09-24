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
- [Troubleshooting](#troubleshooting)

---

## Features

- **GUI Element Localization** — Move the mouse cursor to any visible GUI component (buttons, icons, form fields, menu items, etc.) by describing them in natural language
- **Visual Screen Analysis** — Get a detailed description of the current screen state (open windows, browser tabs, UI elements, disabled controls)
- **Iterative Self-Correction** — Automatically refine cursor position over multiple attempts using a feedback loop: verify → re-estimate → move again
- **Crosshair History Tracking** — Every failed attempt is recorded as a colored marker on the screenshot, building a visual history map
- **Spatial Trajectory Reasoning** — The model analyzes the geometric pattern of all previous crosshair positions to deduce which direction and distance the target lies
- **Human-Like Mouse Movement** — Smooth easing animation (ease-in-out quadratic) with randomized perturbations mimics natural human cursor movement
- **Resolution-Independent Coordinates** — All internal coordinates use a normalized 0–1000 scale, making the system resolution-agnostic
- **Dual-Gate Verification** — A target is only confirmed when both `confirmed` AND `target_at_exact_center` are true, preventing false positives

---

## Project Structure

```
lemme-do-it-for-you/
├── agent/
│   ├── self_correcting_vision_agent.py    # V1/V2 — screen-wide crosshair (legacy)
│   ├── self_correcting_vision_agent_3.py  # V3 — local crosshair + cumulative map + spatial reasoning
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
python -m agent.self_correcting_vision_agent_3
```

### 3. Use Programmatically

```python
from agent.self_correcting_vision_agent_3 import SelfCorrectingVisionAgentV3

agent = SelfCorrectingVisionAgentV3(model_name="qwen3-vl:4b-instruct", verbose=True)

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

### `SelfCorrectingVisionAgentV3` Parameters

```python
SelfCorrectingVisionAgentV3(
    model_name="qwen3-vl:4b-instruct",
    context_window=8192, request_timeout=300.0, max_image_size=1280,
    grid_divisions=5, verbose=True, cleanup_screenshots=True,
)
```

### `locate_element` Parameters

```python
result = agent.locate_element(target="chrome icon", max_iterations=5)
```

Returns a `LocateResult` dataclass with `target`, `x`, `y`, `confidence`, `iterations`, `screen_width`, `screen_height`.

---

## How It Works

### Overview

The agent uses a **visual iterative convergence** loop to locate GUI elements. It combines a multimodal vision model (LLM with image input) with a coordinate system that works entirely in normalized space.

### Workflow

```
STEP 0: Initial Guess -> Capture screen -> Ask LLM for (x, y) coords
    Response: (216, 760) in normalized 0-1000 space
         |
         v
ITERATION LOOP:
  1. MOVE: Normalized -> native pixels (ease-in-out easing)
  2. CAPTURE: Screenshot with grid + crosshair + history + trajectory lines
  3. VERIFY: {confirmed, target_at_exact_center} -> If BOTH true: SUCCESS!
  4. RE-ESTIMATE: Cumulative map + spatial reasoning -> {reasoning, x, y}
  5. UPDATE: Push current position to history (max 6 entries)
```

**Step 1-N:** Normalized `(nx, ny)` converts via `_norm_to_native(nx, ny)`. Screenshot annotated with 4x4 yellow grid, local RED crosshair (25px ticks, 2px dot, 14px ring), colored history points (T1-T6), and trajectory lines. Verify uses strict 4-step reasoning. Re-estimate uses cumulative map.

---

## Coordinate Convergence

### Normalized Coordinate Space (0-1000)

All coordinates use a **normalized 0-1000 space** independent of screen resolution:

- (0, 0) = top-left, (1000, 1000) = bottom-right, (500, 500) = center

**Conversion:** `nx = (x / screen_width) * 1000`

### Convergence Pattern

```
Iteration 1: Crosshair at (216, 760) - target in VLC window
Iteration 2: Crosshair at (350, 550) - model deduced center
Iteration 3: Verified as correct! Result: (672, 594) native, high confidence, 3 iterations
```

- **History acts as learning signal**: Each failed attempt's colored marker provides spatial context
- **Trajectory lines reveal search direction**: Agent can see convergence/divergence
- **Grid labels anchor reasoning**: Yellow grid at (200, 400, 600, 800)

---

## Key Concepts

### 1. Local Crosshair Design

Local ticks instead of screen-wide lines: 25px ticks with 6px gap, 2px center dot, 14px target ring. Prevents visual contact with nearby UI elements.

### 2. Color-Coded History

Up to 6 previous failed attempts as colored markers (T1=cyan, T2=magenta, T3=green, T4=orange, T5=cyan2, T6=pink), each labeled with exact coordinates.

### 3. Cumulative Crosshair Map

Dedicated image showing ALL crosshair positions with trajectory lines. Lets LLM see geometric pattern of search.

### 4. Dual-Gate Verification

```python
if confirmed is True and target_at_exact_center is True:
    return LocateResult(...)  # SUCCESS
```

### 5. Strict Prompt Engineering

Verification: 4-step forced reasoning (identify center, check grid, verify identity, 1-pixel tolerance).
Re-estimation: 4-step spatial deduction (look at all positions, identify directions, find nearest, deduce coordinates).

### 6. Human-Like Mouse Movement

```python
t = pytweening.easeInOutQuad(i / steps)
curr_x = (1-t)**2 * start_x + 2(1-t)*t * mid_x + t**2 * target_x
```

---

## API Reference

### `SelfCorrectingVisionAgentV3`

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

## Troubleshooting

- **Module not found** - Run from project root directory
- **Model timeout** - Check Ollama/OpenRouter, increase `request_timeout`
- **False positives** - Set `cleanup_screenshots=False`, review `iter_*.png`
- **False negatives** - Be more specific, increase `max_iterations` to 8+

### Debugging

```python
agent = SelfCorrectingVisionAgentV3(cleanup_screenshots=False)
result = agent.locate_element(target="my target")
# iter_0.png through iter_N.png preserved in working directory
```

---

## License

MIT
