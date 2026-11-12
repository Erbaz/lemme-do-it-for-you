"""Type text into a UI element by selector."""

import json
import pythoncom
import time
import uiautomation as auto
from langchain_core.tools import tool

from gui_agent.windows.uia.locator import find_element, get_root
from gui_agent.windows.uia.patterns import type_text as type_el
from gui_agent.windows.tools.uia_tools.get_interactable_elements import _collect_interactable
from gui_agent.windows.tools.uia_tools.get_focused_windows import get_focused_windows as _get_focused_windows


def _get_feedback_state() -> str:
    """Get current interactable elements and focused windows for feedback.

    Returns a compact list (name, selector, control_type) so the LLM context
    doesn't balloon with full bounding rectangles for every element.
    """
    pythoncom.CoInitialize()
    desktop = auto.GetRootControl()
    results = []
    _collect_interactable(desktop, results, max_depth=7, verbose=False)
    lines = []
    for r in results[:50]:
        name = r.get("name", "")
        sel = r.get("selector", "")
        ct = r.get("control_type", "")
        lines.append(f'  - "{name}" [{ct}] selector="{sel}"')
    interactable = "\n".join(lines) if lines else "  (none)"

    focused = _get_focused_windows.invoke({})

    return f"""CURRENT UI STATE (top interactable elements):
{interactable}
Focused windows: {focused}"""


@tool
def type_text(selector: str, text: str) -> str:
    """Type text into a UI element by selector.

    After typing, this tool returns the current UI state (interactable
    elements + focused windows) so the agent can see what new elements
    appeared (e.g., search results after typing into a search box).

    Selector examples:
        - "name:Search" - Type into element with Name="Search"
        - "class:Edit" - Type into first Edit control
        - "id:txtUsername" - Type into element with AutomationId="txtUsername"

    Args:
        selector: Element selector string
        text: Text to type

    Returns:
        Success or error message
    """
    try:
        root = get_root()
        element = find_element(root, selector)
        if element is None:
            return (
                f"Element not found: {selector}\n"
                f"{_get_feedback_state()}"
            )

        if type_el(element, text):
            # Give the UI time to react (e.g., search results appear after typing)
            time.sleep(0.5)
            return (
                f"Typed text into: {selector}\n"
                f"{_get_feedback_state()}"
            )
        else:
            return (
                f"Failed to type text into: {selector}\n"
                f"{_get_feedback_state()}"
            )
    except Exception as e:
        return f"Error typing text: {str(e)}"