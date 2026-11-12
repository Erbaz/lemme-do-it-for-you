# GUI Agent: UI Change Watcher & Scanner Plan

## Problem Statement

**Current behavior:** The agent operates on a static snapshot of the UIA tree. When it clicks a menu item that opens a submenu/popup:
1. The popup appears as a **new top-level window** (separate HWND, separate tree)
2. The agent continues searching the **original tree** — never sees the new popup
3. Agent loops retrying the same action because it can't find the expected element

**Root cause:** No mechanism exists to:
- Detect that a UI action triggered a tree change
- Re-scan for new windows/popups after actions
- Make the agent aware of "adjacent trees" (new HWNDs) that appeared

**Goal:** After every GUI interaction tool call (click, key press, type), automatically detect and expose new UI elements so the agent can act on them in the next turn.

---

## Proposed Solution: Post-Action Scanner + Event Watcher

Two lightweight components integrated into the tool execution pipeline:

```
Tool Call (click_element)
    → Execute click
    → **Scanner.run()** — immediate re-scan for new windows/popups
    → **Watcher.check_events()** — drain any UIA events fired during action
    → Return ToolResult + **discovered_changes** (new elements, new windows)
    → Agent receives updated context for next turn
```
---

## Component 1: UIAEventWatcher (Background Listener)

**Purpose:** Subscribe to UIA events globally once at startup. Buffer events for post-action polling.

```python
# gui_agent/windows/uia/event_watcher.py

import queue
import threading
import time
import uiautomation as auto
from dataclasses import dataclass
from typing import Optional
from enum import Enum

class EventType(Enum):
    WINDOW_OPENED = "window_opened"
    WINDOW_CLOSED = "window_closed"
    STRUCTURE_CHANGED = "structure_changed"
    MENU_OPENED = "menu_opened"
    MENU_CLOSED = "menu_closed"

@dataclass
class UIAEvent:
    type: EventType
    element: auto.Control
    timestamp: float

class UIAEventWatcher:
    """Global UIA event listener. Start once at agent init."""
    
    _instance: Optional['UIAEventWatcher'] = None
    _lock = threading.Lock()
    
    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._event_queue: queue.Queue[UIAEvent] = queue.Queue()
        self._running = False
        self._initialized = True
    
    def start(self):
        """Register global callbacks. Call once at startup."""
        if self._running:
            return
        
        auto.SetGlobalEventCallback(auto.UIA_WindowOpenedEventId, self._on_window_opened)
        auto.SetGlobalEventCallback(auto.UIA_WindowClosedEventId, self._on_window_closed)
        auto.SetGlobalEventCallback(auto.UIA_StructureChangedEventId, self._on_structure_changed)
        auto.SetGlobalEventCallback(auto.UIA_MenuOpenedEventId, self._on_menu_opened)
        auto.SetGlobalEventCallback(auto.UIA_MenuClosedEventId, self._on_menu_closed)
        
        self._running = True
    
    def stop(self):
        if not self._running:
            return
        auto.SetGlobalEventCallback(auto.UIA_WindowOpenedEventId, None)
        auto.SetGlobalEventCallback(auto.UIA_WindowClosedEventId, None)
        auto.SetGlobalEventCallback(auto.UIA_StructureChangedEventId, None)
        auto.SetGlobalEventCallback(auto.UIA_MenuOpenedEventId, None)
        auto.SetGlobalEventCallback(auto.UIA_MenuClosedEventId, None)
        self._running = False
    
    def _on_window_opened(self, sender, args):
        self._event_queue.put(UIAEvent(EventType.WINDOW_OPENED, sender, time.time()))
    
    def _on_window_closed(self, sender, args):
        self._event_queue.put(UIAEvent(EventType.WINDOW_CLOSED, sender, time.time()))
    
    def _on_structure_changed(self, sender, args):
        if sender and sender.ClassName in ('Qt5QWindowPopupDropShadowSaveBits', 'MenuControl', 'PopupControl'):
            self._event_queue.put(UIAEvent(EventType.STRUCTURE_CHANGED, sender, time.time()))
    
    def _on_menu_opened(self, sender, args):
        self._event_queue.put(UIAEvent(EventType.MENU_OPENED, sender, time.time()))
    
    def _on_menu_closed(self, sender, args):
        self._event_queue.put(UIAEvent(EventType.MENU_CLOSED, sender, time.time()))
    
    def drain_events(self, max_events: int = 20) -> list[UIAEvent]:
        """Call after each tool action to get pending events."""
        events = []
        for _ in range(max_events):
            try:
                events.append(self._event_queue.get_nowait())
            except queue.Empty:
                break
        return events
---

## Component 2: UIChangeScanner (Post-Action Re-Scan)

**Purpose:** After a tool executes, actively scan for new/discoverable elements that the agent should know about.

```python
# gui_agent/windows/uia/change_scanner.py

import uiautomation as auto
from dataclasses import dataclass, field
from typing import Optional
from gui_agent.windows.uia.event_watcher import UIAEventWatcher, UIAEvent, EventType

@dataclass
class DiscoveredChange:
    """A UI change the agent should be aware of."""
    type: str
    element: auto.Control
    description: str
    selector_hint: dict = field(default_factory=dict)

class UIChangeScanner:
    """Scans for UI changes after tool actions."""
    
    POPUP_CLASSES = {
        'Qt5QWindowPopupDropShadowSaveBits',
        '#32768',
        'Windows.UI.Popup.Popup',
        'MenuControl',
        'PopupControl',
    }
    
    MENU_ITEM_CLASSES = {'MenuItemControl', 'MenuItem'}
    
    def __init__(self, known_window_handles: Optional[set[int]] = None):
        self.known_handles = known_window_handles or set()
        self._refresh_known_handles()
        self.watcher = UIAEventWatcher()
    
    def _refresh_known_handles(self):
        self.known_handles = {
            w.NativeWindowHandle for w in auto.GetRootControl().GetChildren()
            if w.NativeWindowHandle
        }
    
    def scan(self) -> list[DiscoveredChange]:
        """Run after each tool action. Returns actionable changes."""
        changes = []
        changes.extend(self._scan_new_windows())
        changes.extend(self._scan_from_events())
        changes.extend(self._scan_expanded_menus())
        self._refresh_known_handles()
        return changes
    
    def _scan_new_windows(self) -> list[DiscoveredChange]:
        changes = []
        current_handles = {
            w.NativeWindowHandle: w for w in auto.GetRootControl().GetChildren()
            if w.NativeWindowHandle
        }
        
        new_handles = set(current_handles.keys()) - self.known_handles
        for handle in new_handles:
            window = current_handles[handle]
            if window.ClassName in self.POPUP_CLASSES:
                changes.append(DiscoveredChange(
                    type="new_popup_menu",
                    element=window,
                    description=f"New popup menu: {window.Name or window.ClassName}",
                    selector_hint={"class_name": window.ClassName, "name": window.Name}
                ))
            else:
                changes.append(DiscoveredChange(
                    type="new_window",
                    element=window,
                    description=f"New window: {window.Name or window.ClassName}",
                    selector_hint={"class_name": window.ClassName, "name": window.Name}
                ))
        return changes
    
    def _scan_from_events(self) -> list[DiscoveredChange]:
        changes = []
        for event in self.watcher.drain_events():
            if event.type == EventType.WINDOW_OPENED and event.element.ClassName in self.POPUP_CLASSES:
                changes.append(DiscoveredChange(
                    type="new_popup_menu",
                    element=event.element,
                    description=f"Popup opened (event): {event.element.Name or event.element.ClassName}",
                    selector_hint={"class_name": event.element.ClassName, "name": event.element.Name}
                ))
            elif event.type == EventType.STRUCTURE_CHANGED:
                changes.append(DiscoveredChange(
                    type="structure_changed",
                    element=event.element,
                    description=f"Structure changed in {event.element.ClassName}",
                    selector_hint={"class_name": event.element.ClassName}
                ))
            elif event.type == EventType.MENU_OPENED:
                changes.append(DiscoveredChange(
                    type="menu_expanded",
                    element=event.element,
                    description=f"Menu opened: {event.element.Name or event.element.ClassName}",
                    selector_hint={"class_name": event.element.ClassName, "name": event.element.Name}
                ))
        return changes
    
    def _scan_expanded_menus(self) -> list[DiscoveredChange]:
        """Check known windows for newly expanded submenus."""
        return []
```
---

## Integration: Tool Callback Wrapper

**Location:** `gui_agent/windows/tools/uia_tools.py` (base class)

```python
# gui_agent/windows/tools/uia_tools.py

from gui_agent.windows.uia.change_scanner import UIChangeScanner, DiscoveredChange
from gui_agent.common.tools.base_tool import ToolResult

_scanner = UIChangeScanner()

class UIAToolBase(BaseTool):
    """Base class for all UIA tools with post-action change scanning."""
    
    def execute(self, **kwargs) -> ToolResult:
        result = self._execute_action(**kwargs)
        
        if result.success:
            changes = _scanner.scan()
            if changes:
                result.metadata = result.metadata or {}
                result.metadata["ui_changes"] = [
                    {
                        "type": c.type,
                        "description": c.description,
                        "selector_hint": c.selector_hint,
                        "element_bounds": c.element.BoundingRectangle if c.element else None
                    }
                    for c in changes
                ]
        
        return result
    
    def _execute_action(self, **kwargs) -> ToolResult:
        raise NotImplementedError
```

---

## Agent Integration: Expose Changes to LLM

**In ReAct loop (base_agent.py):**

```python
# After tool execution, before next LLM call
tool_result = tool_node.execute(tool_call)

if tool_result.metadata and "ui_changes" in tool_result.metadata:
    changes_summary = "\n".join(
        f"- {c['type']}: {c['description']} (hint: {c['selector_hint']})"
        for c in tool_result.metadata["ui_changes"]
    )
    state.add_observation(
        f"UI CHANGES DETECTED:\n{changes_summary}\n"
        f"Consider these new elements for your next action."
    )
```

---

## Configuration (config/windows.yaml)

```yaml
uia:
  change_scanner:
    enabled: true
    scan_after_tools: ["click_element", "double_click", "press_key", "type_text", "send_hotkey"]
    max_events_per_scan: 20
    popup_classes:
      - "Qt5QWindowPopupDropShadowSaveBits"
      - "#32768"
      - "MenuControl"
      - "PopupControl"
```

---

## Testing the Plan

### Unit Tests
```python
# tests/unit/test_change_scanner.py
def test_detects_qt_popup_after_click():
    scanner = UIChangeScanner()
    click_media_menu()
    changes = scanner.scan()
    assert any(c.type == "new_popup_menu" for c in changes)

def test_event_watcher_captures_window_opened():
    watcher = UIAEventWatcher()
    watcher.start()
    open_context_menu()
    events = watcher.drain_events()
    assert any(e.type == EventType.WINDOW_OPENED for e in events)
```

### Manual Test
```bash
python main.py "<your task>" 2>&1 | grep -A5 "UI CHANGES"
```

---

## What This Solves

| Before | After |
|--------|-------|
| Agent clicks a menu → loops, never sees submenu | Agent clicks → scanner detects new popup → LLM sees "new_popup_menu: submenu" → next action targets ListControl inside it |
| Agent unaware of new dialogs/popups | Every tool call returns `ui_changes` metadata |
| No event awareness | Global watcher buffers events, scanner drains them post-action |

---

## Scope & Non-Goals

**In scope:**
- Post-action scanning for new windows/popups
- UIA event buffering for menu/window open events
- Injecting discovered changes into agent context
- Works for Qt, Win32, UWP popup patterns

**Out of scope:**
- Full tree diffing (too expensive)
- Visual/OCR fallback (separate concern)
- Cross-process UIA caching (complexity)
- Predictive pre-scanning (not needed)

---

## Implementation Order

1. **`event_watcher.py`** — Global listener, start/stop, event queue
2. **`change_scanner.py`** — Post-action scan logic, known_handles tracking
3. **Modify `UIAToolBase`** — Call scanner after successful actions
4. **Update `base_agent.py`** — Inject `ui_changes` into observation
5. **Add config** — Enable/disable, tool list, popup classes
6. **Tests** — Unit + manual verification
```