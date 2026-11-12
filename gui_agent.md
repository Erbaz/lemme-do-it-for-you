# GUI Agent — Milestone 1

## High-Level Understanding of Tool Calling

The agent uses a **ReAct loop** (LangGraph `create_react_agent`) to drive Windows GUI automation via UI Automation (UIA). The flow is:

1. **Context gathering** — The agent calls `get_top_level_windows()`, `get_interactable_elements()`, or `read_accessibility_tree()` to understand what is on screen before acting.
2. **Element identification** — The agent uses `find_element_tool()` or `find_elements_tool()` with selectors like `name:Start`, `name:Search`, `name:Search box` to locate a specific UI element and obtain its bounding rectangle.
3. **Physical click** — `click_element()` moves the physical mouse cursor to the element's bounding-box center (via `SetCursorPos`), waits 0.5s, then performs a physical left-click (via `mouse_event` with `MOUSEEVENTF_ABSOLUTE`). After clicking, it returns the current UI state (interactable elements + focused windows) so the agent sees what new UI appeared.
4. **Text input** — `type_text()` focuses the element via UIA patterns and sends keystrokes. After typing, it returns the current UI state so the agent can see newly appeared elements (e.g., search results).
5. **Verification** — The agent re-checks `get_top_level_windows()` to confirm the target application window appeared.

## What Won

| Area | Detail |
|------|--------|
| **Agent framework** | Reverted from `create_deep_agent` (Deep Agents) to `create_react_agent` (LangGraph). Deep Agents caused over-exploration, todo-list planning loops, and incorrect tool selection (e.g., using `grep` instead of clicking UI elements). The plain ReAct loop is more deterministic for GUI automation. |
| **Mouse movement** | `move_mouse()` now uses `SetCursorPos(x, y)` instead of `SendInput` with normalized coordinates. Previously `SendInput` returned success but the cursor never physically moved. Now the cursor reliably moves to the element's center. |
| **Mouse click** | `mouse_click()` now uses `mouse_event` with `MOUSEEVENTF_ABSOLUTE` + normalized coordinates instead of `SendInput` with relative `dx=0, dy=0`. Previously Windows never processed it as a real click at the cursor location. Now the Start Menu opens when clicking the Start button. |
| **Click timing** | `click_element()` waits 0.5s after moving the mouse before clicking, giving the cursor time to settle. |
| **Feedback state** | `click_element()` and `type_text()` return a trimmed `CURRENT UI STATE` block after every action (interactable elements + focused windows). This lets the agent see what new UI elements appeared (e.g., Start Menu, Search box) and correct its selector if needed. The output is capped at 50 elements with only `name`, `control_type`, and `selector` to prevent LLM context bloat. |
| **Tool registry** | Removed `launch_app` (unreliable fallback) and `mouse_move` (agent should use `click_element`). Tool count reduced to 15. |
| **End-to-end success** | The agent successfully opened Notepad: clicked Start → opened Start Menu → clicked Search → typed "notepad" → found "Untitled - Notepad" in top-level windows → confirmed task complete. |

## What Did Not Work

| Area | Detail |
|------|--------|
| **Start Menu via UIA InvokePattern** | Pure UIA `Invoke()` on the Start button does not reliably open the Start Menu. Physical mouse click via `click_element()` is required. |
| **`type_text` without physical click** | `type_text()` previously used UIA `ValuePattern`/`SetFocus`+`SendKeys` without clicking first. Windows 11's modern XAML search box often doesn't respond to pure UIA text injection. The agent now physically clicks via `click_element()` before typing. |
| **Launching via `launch_app`** | Removed because the Start Menu path now works via physical clicks. Direct executable path was brittle across different installations. |
| **`grep` tool misuse** | Deep Agents would call `grep` (code-search tool) instead of UIA tools when trying to locate UI elements. Eliminated by switching to plain ReAct. |
| **LLM rate limits** | Free-tier OpenRouter models (`nvidia/nemotron-3.5-lightning:free`, `liquid/lfm-3-1.7b:free`) hit 429 rate limits quickly, especially with large feedback-state context. Each LLM turn takes 3–60 seconds. |

## Current Tool Registry (15 tools)

`echo`, `get_time`, `click_element`, `type_text`, `find_element_tool`, `find_elements_tool`, `read_accessibility_tree`, `get_focused_element_info`, `get_element_at_point`, `scroll_element`, `expand_element`, `collapse_element`, `get_top_level_windows`, `get_focused_windows`, `get_interactable_elements`
