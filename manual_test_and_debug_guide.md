# GUI Agent: Manual Test & Debug Guide

## What Has Been Implemented

### Project Structure
```
lemme-do-it-for-you/gui_agent/
├── main.py                      # Entry point, CLI
├── pyproject.toml               # Dependencies
├── config/
│   ├── settings.yaml            # Global configuration
│   └── windows.yaml             # Windows-specific settings
├── common/
│   ├── agent/
│   │   ├── base_agent.py        # RpaAgent (LangGraph ReAct)
│   │   ├── decision_maker.py    # GuiDecisionMaker (future)
│   │   ├── state.py             # AgentState, WorkflowMemory
│   │   └── callbacks/
│   │       ├── action_indexer.py    # Action pattern indexing
│   │       ├── workflow_learner.py  # Workflow pattern extraction
│   │       └── humanizer.py         # Human-like input simulation
│   ├── tools/
│   │   ├── base_tool.py         # BaseTool with platform detection
│   │   ├── registry.py          # ToolRegistry (platform-aware)
│   │   └── schemas.py           # Tool I/O schemas
│   ├── platform/
│   │   ├── detector.py          # OS detection
│   │   └── capabilities.py      # Platform capabilities
│   ├── input/
│   │   ├── mouse.py             # Humanized mouse (Bezier curves)
│   │   ├── keyboard.py          # Humanized keyboard (bursts, typos)
│   │   └── gestures.py          # Drag, scroll, select
│   └── utils/
│       └── logging.py           # Structured logging
├── windows/
│   ├── tools/
│   │   ├── uia_tools.py         # UIA: click, type, find, scroll (with post-action change scanning)
│   │   ├── window_tools.py      # Window focus, move, resize
│   │   ├── input_tools.py       # Keys, hotkeys, clipboard
│   │   └── system_tools.py      # PowerShell
│   ├── uia/
│   │   ├── client.py            # UIA client wrapper
│   │   ├── event_watcher.py     # Global UIA event listener + event queue
│   │   └── change_scanner.py    # Post-action UI change scanner
│   └── input/
│       ├── mouse.py             # SendInput mouse
│       └── keyboard.py          # SendKeys keyboard
├── tests/
│   └── unit/
│       └── test_change_scanner.py   # Functional unit tests for change scanner
└── scripts/
    └── record_workflow.py       # Manual workflow recording
```

### Core Components Working

| Component | Status | Description |
|-----------|--------|-------------|
| **UIA Client** | Working | Finds elements via UI Automation |
| **Element Discovery** | Working | Finds windows, menus, and UI elements |
| **Tool Registry** | Working | Loads Windows tools dynamically |
| **Humanizer** | Working | Bezier curves, burst typing, micro-pauses |
| **Action Indexer** | Working | SQLite storage for action patterns |
| **LangGraph ReAct** | Working | Agent reasoning loop |
| **UIA Event Watcher** | Working | Global UIA event listener with buffered queue |
| **UI Change Scanner** | Working | Post-action scan for new windows/popups |

---

## How to Test the UI Change Scanner

### 0. Install Dependencies (if needed)

If you get `ModuleNotFoundError` (e.g. `structlog`), your activated venv is missing dependencies. Install them:

```powershell
cd C:/Users/pc/Desktop/lemme-do-it-for-you; .venv/Scripts/pip.exe install structlog langgraph langchain-core langchain-openai pyyaml uiautomation comtypes
```

If `pip.exe` times out or is not available, use the **system python** instead (it already has the deps):

```powershell
cd C:/Users/pc/Desktop/lemme-do-it-for-you; python -m pip install --user structlog langgraph langchain-core langchain-openai pyyaml uiautomation comtypes
```

> **Important:** Always run from the **project root** (`lemme-do-it-for-you/`), not inside `gui_agent/`. Running `python gui_agent/main.py` from the project root ensures `sys.path` includes the project root so `import gui_agent...` works.

### 1. Run Unit Tests

Run the functional unit tests for the change scanner:

```powershell
cd C:/Users/pc/Desktop/lemme-do-it-for-you; python -c "import sys; sys.path.insert(0, '.'); loader = __import__('unittest').TestLoader(); suite = loader.discover('gui_agent/tests/unit', pattern='test_change_scanner.py'); runner = __import__('unittest').TextTestRunner(verbosity=2); runner.run(suite)"
```

Expected output: all 11 tests pass (`Ran 11 tests ... OK`).

### 2. Run the Agent with UI Change Detection

Run from the **project root** (not inside `gui_agent/`):

```powershell
cd C:/Users/pc/Desktop/lemme-do-it-for-you; python gui_agent/main.py "<your task>" --verbose 2>&1 | Select-String -Pattern "UI CHANGES" -Context 0,10
```

**To see all live agent logs** (thoughts, actions, results, UI changes) — do NOT filter:

```powershell
cd C:/Users/pc/Desktop/lemme-do-it-for-you; python gui_agent/main.py "<your task>" --verbose
```

Example task: `"Open the calculator and click the plus button"`.

**If you see no output:** Either the LLM never made a tool call, or the process exited early. Check:
- `OPENROUTER_API_KEY` environment variable is set
- Look at `logs/gui-agent.log` for full logs
- Run without `Select-String` to see raw output

### 3. Verify `ui_changes` Metadata in Tool Results

From Python, verify that a successful tool call returns `ui_changes` metadata when a new popup appears:

```python
from gui_agent.windows.tools.uia_tools import ClickElementTool
from gui_agent.common.tools.schemas import ElementSelector, ElementRole

tool = ClickElementTool({})
result = tool.execute(
    selector=ElementSelector(name="Some Menu", role=ElementRole.MENU_ITEM)
)

# Check for ui_changes metadata
if result.metadata and "ui_changes" in result.metadata:
    for change in result.metadata["ui_changes"]:
        print(f"Change: {change['type']} - {change['description']}")
        print(f"  Hint: {change['selector_hint']}")
        print(f"  Bounds: {change['element_bounds']}")
else:
    print("No UI changes detected (or tool did not succeed)")
```

### 4. Inspect the Change Scanner Directly

Test the scanner standalone without running the full agent:

```python
from gui_agent.windows.uia.change_scanner import UIChangeScanner

scanner = UIChangeScanner()
changes = scanner.scan()
for c in changes:
    print(f"{c.type}: {c.description}")
```

### 5. Config

The change scanner is configured in `config/windows.yaml`:

```yaml
uia:
  change_scanner:
    enabled: true
    scan_after_tools: ["click_element", "double_click", "press_key", "type_text", "send_hotkey"]
    max_events_per_scan: 20
    popup_classes:
      - "Qt5QWindowPopupDropShadowSaveBits"
      - "#32768"
      - "Windows.UI.Popup.Popup"
      - "MenuControl"
      - "PopupControl"
```

Disable scanning by setting `enabled: false`.
