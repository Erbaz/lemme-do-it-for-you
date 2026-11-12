# gui_agent_developer

How to work on the Windows GUI Automation Agent (`gui_agent/`).

## Context gathering — required before any change

Before editing anything, refresh your understanding of the current project state:

1. **Read `gui_agent.md`** — Milestone 1 notes on what works, what doesn't, and the current tool registry.
2. **Read `gui_agent/sys_prompt.py`** — the system prompt that governs agent behavior. Do not modify it without asking the user.
3. **Read `gui_agent/main.py`** — the CLI entry point. Check `load_tools()` to see which tools are registered.
4. **Read `gui_agent/tools.py`** — aggregates all `@tool` functions from `gui_agent/windows/tools/uia_tools/`.
5. **Read `gui_agent/common/agent/base_agent.py`** — how the agent is constructed (`langchain_create_agent`).
6. **List `gui_agent/windows/tools/uia_tools/`** — see exactly which tool files exist. Do not assume.
7. **Check `gui_agent/.logs/`** — most recent run log to see what the agent actually did (tool calls, selectors, errors).

## Working principles

### 1. Ask before acting
- If the user's request is ambiguous, ask. Do not assume intent.
- Before changing `sys_prompt.py`, `main.py`, `tools.py`, or `base_agent.py`, confirm the change with the user.
- Before testing via `main.py` with a prompt, ask the user what task prompt to use. Do not invent test tasks.

### 2. Test directly, not through the agent
- Test individual tools directly (e.g., `click_element.invoke({'selector': 'name:Start'})`) before testing through the agent.
- Verify mouse movement and click registration with `get_mouse_position()` before/after.
- Only after tool-level verification passes, run through `main.py` with a user-approved task.

### 3. Separation of Concerns
- Each tool file in `uia_tools/` does one thing. Do not bloat files or functions.
- If a function exceeds ~50 lines, split it.
- Keep `patterns.py` as thin wrappers around UIA pattern objects. Keep business logic in `uia_tools/`.
- `click_element` does physical move + click + UI state feedback. It does NOT do InvokePattern or SelectionItemPattern.
- `type_text` types text. It does not click first — that's `click_element`'s job.

### 4. Keep it simple
- Before writing code, read the relevant documentation or library source (e.g., `uiautomation`, `langgraph.prebuilt.create_react_agent`).
- If something seems complex, step back and check if a simpler approach exists (e.g., `SetCursorPos` instead of `SendInput` normalized coordinates).
- Prefer reading existing code over guessing.

## File responsibilities

| File | Responsibility |
|------|---------------|
| `gui_agent/main.py` | CLI entry, LLM loading, agent creation, timeout wrapper |
| `gui_agent/sys_prompt.py` | System prompt — agent behavior instructions |
| `gui_agent/tools.py` | Tool registry imports + `__all__` |
| `gui_agent/common/agent/base_agent.py` | `langchain_create_agent()` factory |
| `gui_agent/common/input/mouse.py` | `move_mouse()`, `mouse_click()`, `get_mouse_position()` |
| `gui_agent/windows/uia/patterns.py` | Thin UIA pattern wrappers (invoke, set_value, scroll, etc.) |
| `gui_agent/windows/uia/locator.py` | `find_element()`, `get_root()`, `build_selector()` |
| `gui_agent/windows/tools/uia_tools/click_element.py` | Physical move + click + feedback state |
| `gui_agent/windows/tools/uia_tools/type_text.py` | Type text + feedback state |
| `gui_agent/windows/tools/uia_tools/*.py` | One tool per file |

## Common mistakes to avoid

- **Testing via `main.py` without asking** — always confirm the test prompt with the user first.
- **Manual testing without checking expected output** — know what you want to see before you run.
- **Bloating functions** — keep functions small and single-purpose.
- **Overcomplicating** — check docs/library source before assuming complexity is needed.
- **Modifying `sys_prompt.py` without asking** — it governs all agent behavior.
