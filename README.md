# Lemme Do It For You — Windows GUI Automation Agent

A Windows GUI automation agent that controls desktop applications through UI Automation (UIA) and a LangGraph ReAct agent. It launches applications, navigates menus, clicks buttons, and types into fields using physical mouse movement and clicks — not just UIA API calls.

![License](https://img.shields.io/badge/License-MIT-green)

---

## Table of Contents

- [Features](#features)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [How It Works](#how-it-works)
- [Tools](#tools)
- [Example Workflows](#example-workflows)
- [Milestone 1 — Agent Tool Calling Analysis](#milestone-1)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## Features

- **Physical mouse clicks** — Moves the cursor to an element's bounding-box center via `SetCursorPos`, then clicks via `mouse_event` with `MOUSEEVENTF_ABSOLUTE`. Works where pure UIA `InvokePattern` fails (e.g., Windows Start button).
- **Accessibility tree exploration** — `get_top_level_windows()`, `get_interactable_elements()`, `read_accessibility_tree()` to discover UI elements and their selectors.
- **Feedback state after every action** — `click_element()` and `type_text()` return a trimmed `CURRENT UI STATE` block so the agent sees what new UI appeared after each action.
- **Selector-based targeting** — `name:`, `class:`, `id:` (automation_id), or combined selectors.
- **Double-click support** — For Start Menu items and other elements that need activation.
- **ReAct agent** — LangGraph `create_react_agent` loop with `reasoning_effort="low"` for deterministic tool use.
- **Timeout protection** — Agent invocations run in a thread with a configurable timeout.

---

## Project Structure

```
lemme-do-it-for-you/
├── gui_agent/
│   ├── main.py              # CLI entry point
│   ├── sys_prompt.py        # System prompt for the agent
│   ├── tools.py             # Tool registry (aggregates all @tool functions)
│   ├── pyproject.toml       # Package config & dependencies
│   ├── __init__.py
│   ├── common/
│   │   ├── __init__.py
│   │   ├── agent/
│   │   │   ├── __init__.py
│   │   │   ├── base_agent.py      # langchain_create_agent() factory
│   │   │   ├── callbacks.py       # GuiAgentCallbackHandler
│   │   │   └── state.py           # AgentState TypedDict
│   │   ├── input/
│   │   │   ├── mouse.py           # move_mouse(), mouse_click(), get_mouse_position()
│   │   │   ├── keyboard.py        # send_keys()
│   │   │   └── __init__.py
│   │   ├── platform/
│   │   │   ├── detector.py        # PlatformDetector
│   │   │   └── capabilities.py
│   │   ├── utils/
│   │   │   ├── logging.py         # setup_logging()
│   │   │   └── file_logging.py    # per-run timestamped log files
│   │   └── __init__.py
│   ├── windows/
│   │   ├── __init__.py
│   │   ├── uia/
│   │   │   ├── __init__.py
│   │   │   ├── locator.py         # find_element(), get_root(), build_selector()
│   │   │   └── patterns.py        # invoke(), set_value(), scroll(), etc.
│   │   └── tools/
│   │       ├── __init__.py
│   │       └── uia_tools/
│   │           ├── __init__.py
│   │           ├── click_element.py     # Physical move + click + UI state feedback
│   │           ├── type_text.py         # Type + UI state feedback
│   │           ├── find_element.py      # find_element_tool
│   │           ├── find_elements.py     # find_elements_tool
│   │           ├── mouse_click.py       # mouse_click (standalone)
│   │           ├── read_accessibility_tree.py
│   │           ├── get_focused_element_info.py
│   │           ├── get_element_at_point.py
│   │           ├── scroll_element.py
│   │           ├── expand_element.py
│   │           ├── collapse_element.py
│   │           ├── get_top_level_windows.py
│   │           ├── get_focused_windows.py
│   │           └── get_interactable_elements.py
│   └── .logs/               # Per-run timestamped log files (gitignored)
├── gui_agent.md             # Detailed implementation notes & Milestone 1
├── gui-agent-plan.md        # Project plan
├── README.md                # This file
├── requirements.txt         # Python dependencies
├── .env                     # API keys & model config (gitignored)
├── .gitignore
└── .env                     # Environment variables (gitignored)
```

---

## Quick Start

### Prerequisites

- Python 3.10+
- Windows (UIA is Windows-only)
- OpenRouter API key (or another supported LLM provider)

### 1. Install Dependencies

```bash
cd c:\Users\pc\Desktop\lemme-do-it-for-you
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e gui_agent/
```

### 2. Configure Environment

Create a `.env` file at the project root:

```
MODEL_PROVIDER=openrouter
MODEL_NAME=nvidia/nemotron-3.5-lightning:free
OPENROUTER_API_KEY=your-api-key-here
LOG_LEVEL=INFO
```

### 3. Run the Agent

```bash
python gui_agent/main.py "Open Notepad" --timeout=120
```

The agent will:
1. Check what windows are currently running
2. Launch the app via Start Menu if needed
3. Verify the app appeared
4. Report success

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_PROVIDER` | `openrouter` | `openrouter`, `openai`, or `ollama` |
| `MODEL_NAME` | `dots-studio/dots-3-note-preview:free` | Model identifier |
| `OPENROUTER_API_KEY` | *(required)* | Your OpenRouter API key |
| `OPENAI_API_KEY` | *(optional)* | Fallback for OpenRouter or OpenAI provider |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `OPENAI_BASE_URL` | `https://openrouter.ai/api/v1` | API base URL |

### Supported Providers

- **openrouter** — `https://openrouter.ai/api/v1`
- **openai** — `https://api.openai.com/v1`
- **ollama** — `http://localhost:11434/v1`
```

This starts the Imajev decision server at `http://localhost:8765` (OpenAI-compatible `POST /v1/systemone`) that the V6 agent calls for single-inference presence confirmations during crop-and-zoom convergence.

## How It Works

### Architecture

The agent is a **LangGraph ReAct loop** (`create_react_agent`) with a custom system prompt. It does not use Deep Agents (which caused over-exploration and wrong tool selection).

### Click Pipeline

Every `click_element` call follows this sequence:

1. **Find element** � Locate the UI element by selector (`name:`, `class:`, `id:`)
2. **Verify tree** � Read the element's accessibility tree to confirm it has content
3. **Move mouse** � `SetCursorPos()` to the element's bounding-box center
4. **Settle** � Wait 0.5s for the cursor to stabilize
5. **Click** � `mouse_event()` with `MOUSEEVENTF_LEFTDOWN | ABSOLUTE`, then `LEFTUP | ABSOLUTE`
6. **Report** � Return `Clicked element: <selector>` + compact `CURRENT UI STATE`

### Type Pipeline

1. **Find element** � Locate the input field
2. **Type** � Send keystrokes via UIA patterns
3. **Settle** � Wait 0.5s for UI to react (e.g., search results)
4. **Report** � Return `Typed text into: <selector>` + `CURRENT UI STATE`

### Feedback State

After every action, the tool returns a trimmed UI snapshot:

```
CURRENT UI STATE (top interactable elements):
  - "Search" [WindowControl] selector="name:Search"
  - "Search box" [EditControl] selector="id:SearchTextBox"
  - "Taskbar" [PaneControl] selector="name:Taskbar"
Focused windows:
  {
    "name": "Search",
    "focused_control_name": "Search box",
    ...
  }
```

This lets the agent see what new elements appeared (e.g., Start Menu, Search box) and correct its next action.

---

## Tools

| Tool | Description |
|------|-------------|
| `click_element(selector, double_click=False)` | Move mouse to element center + physical left-click |
| `type_text(selector, text)` | Type text into an input field |
| `find_element_tool(selector)` | Find a single element by selector |
| `find_elements_tool(selector)` | Find all elements matching a selector |
| `read_accessibility_tree(selector, depth, verbose)` | Read UIA tree from root or a specific element |
| `get_top_level_windows(verbose)` | List all top-level windows |
| `get_focused_windows()` | Get the currently focused window |
| `get_interactable_elements(scope, max_depth, verbose)` | List all clickable/typeable elements |
| `get_focused_element_info()` | Get info about the focused element |
| `get_element_at_point(x, y)` | Get element at screen coordinates |
| `scroll_element(selector, direction, amount)` | Scroll an element |
| `expand_element(selector)` | Expand a tree item/combo box |
| `collapse_element(selector)` | Collapse a tree item/combo box |
| `mouse_click(button="left")` | Physical mouse click at current position |
| `echo(text)` | Test tool — echo input |
| `get_time()` | Test tool — current time |

---

## Example Workflows

### Launch Notepad

```
Task: Open Notepad

1. get_top_level_windows() → Notepad not running
2. get_interactable_elements(scope="desktop") → Found Taskbar
3. click_element("name:Start") → Start Menu opens
4. click_element("name:Search", double_click=True) → Search overlay opens
5. type_text("name:Search box", "notepad") → Search results appear
6. get_top_level_windows() → "Untitled - Notepad" found
7. ✅ Task complete
```

### Open File in VLC

```
Task: Open VLC, select Media → Open File

1. get_top_level_windows() → VLC not running
2. click_element("name:Start") → Start Menu opens
3. type_text("name:Search box", "vlc") → VLC result appears
4. click_element("name:VLC media player", double_click=True) → VLC launches
5. get_top_level_windows() → VLC confirmed running
6. read_accessibility_tree("name:VLC media player") → Found "Media Alt+M" menu
7. click_element("name:Media Alt+M") → Media dropdown opens
8. get_interactable_elements(scope="foreground") → Found "Open File... Ctrl+O"
9. click_element("name:Open File... Ctrl+O") → File dialog opens
10. ✅ Task complete
```

---

## Milestone 1 — Agent Tool Calling Analysis

### High-Level Understanding of Tool Calling

The agent uses a **ReAct loop** (LangGraph `create_react_agent`) to drive Windows GUI automation via UI Automation (UIA). The flow is:

1. **Context gathering** — The agent calls `get_top_level_windows()`, `get_interactable_elements()`, or `read_accessibility_tree()` to understand what is on screen before acting.
2. **Element identification** — The agent uses `find_element_tool()` or `find_elements_tool()` with selectors like `name:Start`, `name:Search`, `name:Search box` to locate a specific UI element and obtain its bounding rectangle.
3. **Physical click** — `click_element()` moves the physical mouse cursor to the element's bounding-box center (via `SetCursorPos`), waits 0.5s, then performs a physical left-click (via `mouse_event` with `MOUSEEVENTF_ABSOLUTE`). After clicking, it returns the current UI state (interactable elements + focused windows) so the agent sees what new UI appeared.
4. **Text input** — `type_text()` focuses the element via UIA patterns and sends keystrokes. After typing, it returns the current UI state so the agent can see newly appeared elements (e.g., search results).
5. **Verification** — The agent re-checks `get_top_level_windows()` to confirm the target application window appeared.

### What Won

| Area | Detail |
|------|--------|
| **Agent framework** | Reverted from `create_deep_agent` (Deep Agents) to `create_react_agent` (LangGraph). Deep Agents caused over-exploration, todo-list planning loops, and incorrect tool selection (e.g., using `grep` instead of clicking UI elements). The plain ReAct loop is more deterministic for GUI automation. |
| **Mouse movement** | `move_mouse()` now uses `SetCursorPos(x, y)` instead of `SendInput` with normalized coordinates. Previously `SendInput` returned success but the cursor never physically moved. Now the cursor reliably moves to the element's center. |
| **Mouse click** | `mouse_click()` now uses `mouse_event` with `MOUSEEVENTF_ABSOLUTE` + normalized coordinates instead of `SendInput` with relative `dx=0, dy=0`. Previously Windows never processed it as a real click at the cursor location. Now the Start Menu opens when clicking the Start button. |
| **Click timing** | `click_element()` waits 0.5s after moving the mouse before clicking, giving the cursor time to settle. |
| **Feedback state** | `click_element()` and `type_text()` return a trimmed `CURRENT UI STATE` block after every action (interactable elements + focused windows). This lets the agent see what new UI elements appeared (e.g., Start Menu, Search box) and correct its selector if needed. The output is capped at 50 elements with only `name`, `control_type`, and `selector` to prevent LLM context bloat. |
| **Tool registry** | Removed `launch_app` (unreliable fallback) and `mouse_move` (agent should use `click_element`). Tool count reduced to 15. |
| **End-to-end success** | The agent successfully opened Notepad: clicked Start → opened Start Menu → clicked Search → typed "notepad" → found "Untitled - Notepad" in top-level windows → confirmed task complete. |

### What Did Not Work

| Area | Detail |
|------|--------|
| **Start Menu via UIA InvokePattern** | Pure UIA `Invoke()` on the Start button does not reliably open the Start Menu. Physical mouse click via `click_element()` is required. |
| **`type_text` without physical click** | `type_text()` previously used UIA `ValuePattern`/`SetFocus`/`SendKeys` without clicking first. Windows 11's modern XAML search box often doesn't respond to pure UIA text injection. The agent now physically clicks via `click_element()` before typing. |
| **Launching via `launch_app`** | Removed because the Start Menu path now works via physical clicks. Direct executable path was brittle across different installations. |
| **`grep` tool misuse** | Deep Agents would call `grep` (code-search tool) instead of UIA tools when trying to locate UI elements. Eliminated by switching to plain ReAct. |
| **LLM rate limits** | Free-tier OpenRouter models (`nvidia/nemotron-3.5-lightning:free`, `liquid/lfm-3-1.7b:free`) hit 429 rate limits quickly, especially with large feedback-state context. Each LLM turn takes 3–60 seconds. |

### Current Tool Registry (15 tools)

`echo`, `get_time`, `click_element`, `type_text`, `find_element_tool`, `find_elements_tool`, `read_accessibility_tree`, `get_focused_element_info`, `get_element_at_point`, `scroll_element`, `expand_element`, `collapse_element`, `get_top_level_windows`, `get_focused_windows`, `get_interactable_elements`

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ImportError: cannot import name 'create_agent'` | Fixed — uses `langgraph.prebuilt.create_react_agent` now |
| Start Menu doesn't open | `click_element` now physically clicks; verify `SetCursorPos` works |
| Click doesn't register | `mouse_click` uses `mouse_event` with `MOUSEEVENTF_ABSOLUTE` |
| Agent can't find search box | Feedback state shows actual control types — use `name:`, `id:`, or `class:` accordingly |
| 429 rate limit | Free OpenRouter tier is rate-limited; use a paid model or wait |
| No `.env` | Create one with `MODEL_PROVIDER`, `MODEL_NAME`, `OPENROUTER_API_KEY` |
| Log files | Per-run logs in `gui_agent/.logs/` |

---

## License

MIT
