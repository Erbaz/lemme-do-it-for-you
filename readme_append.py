filepath = r'C:\Users\pc\Desktop\lemme-do-it-for-you\README.md'
with open(filepath, 'a') as f:
    f.write("""

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

| Function | Description |
|---|---|
| `move_mouse(prompt)` | Move cursor to target GUI element |
| `analyze_screen(prompt)` | Describe current screen state |
| `left_click()` | Click at current cursor position |
| `right_click()` | Right-click at current cursor position |
| `double_click()` | Double-click at current cursor position |
| `type_text(text)` | Type text with human-like delays |
| `press_key(key)` | Press a single key |
| `execute_hotkey(keys)` | Execute keyboard hotkey combo |

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
""")
print('Done!')
