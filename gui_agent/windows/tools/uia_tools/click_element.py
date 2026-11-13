"""Click a UI element by selector - pure physical mouse click with accessibility tree verification."""

import time
from langchain_core.tools import tool
from typing import Optional

import structlog

from gui_agent.windows.uia.locator import find_element, get_root
from gui_agent.common.input import move_mouse, mouse_click
from gui_agent.windows.uia.patterns import get_bounding_rectangle
from gui_agent.common.selector_tracker import selector_tracker
from gui_agent.windows.tools.uia_tools.read_accessibility_tree import _build_tree
from gui_agent.windows.tools.uia_tools.get_interactable_elements import _collect_interactable
from gui_agent.windows.tools.uia_tools.get_focused_windows import get_focused_windows as _get_focused_windows
import uiautomation as auto
import pythoncom
import json

logger = structlog.get_logger(__name__)


def _get_feedback_state() -> str:
    """Get current interactable elements and focused windows for feedback.

    Returns a compact list (name, selector, control_type) so the LLM context
    doesn't balloon with full bounding rectangles for every element.
    """
    pythoncom.CoInitialize()
    desktop = auto.GetRootControl()
    results = []
    _collect_interactable(desktop, results, max_depth=5, verbose=False)
    # Compact: just name + selector + control_type per element
    lines = []
    for r in results[:50]:  # Cap at 50 to avoid context bloat
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
def click_element(selector: str, double_click: bool = False) -> str:
    """Click a UI element by selector using physical mouse movement and click.

    Before clicking, this tool reads the accessibility tree of the target
    element to verify it has expected children/content. If the tree is empty
    or the element cannot be found, it returns an error message with current
    UI state feedback (interactable elements + focused windows) so the agent
    can correct its selector.

    This tool does NOT use UIA InvokePattern or SelectionItemPattern.
    It finds the element's bounding box, moves the physical mouse cursor
    to the center of that box, then performs a physical mouse click.

    Selector examples:
        - "name:Submit" - Click element with Name="Submit"
        - "class:Button" - Click first Button class element
        - "id:btnLogin" - Click element with AutomationId="btnLogin"
        - "name:Login,class:Button" - Click Button with Name="Login"

    Args:
        selector: Element selector string
        double_click: If True, perform double-click (useful for Start Menu items)

    Returns:
        Success or error message
    """
    if selector_tracker.is_failed(selector):
        return f"Selector previously failed: {selector}"

    try:
        root = get_root()
        element = find_element(root, selector)
        if element is None:
            selector_tracker.record_failure(selector)
            return (
                f"Selector is not correct: element not found for '{selector}'.\n"
                f"Try exploring the accessibility tree to see what elements are available.\n"
                f"{_get_feedback_state()}"
            )

        # Read the accessibility tree of the target element to verify it has content
        tree = _build_tree(element, 1, 5, verbose=True)
        if not tree or (not tree.get("children") and not tree.get("name")):
            selector_tracker.record_failure(selector)
            return (
                f"Selector is not correct: '{selector}' has no accessible children.\n"
                f"Try exploring the accessibility tree to see what elements are available.\n"
                f"{_get_feedback_state()}"
            )

        rect = get_bounding_rectangle(element)
        if not rect:
            selector_tracker.record_failure(selector)
            return f"Element has no bounding rectangle: {selector}"

        center_x = (rect.left + rect.right) // 2
        center_y = (rect.top + rect.bottom) // 2
        logger.info(f"Moving mouse to ({center_x}, {center_y}) for element: {selector}")
        move_mouse(center_x, center_y)

        # Wait for cursor movement to complete before clicking
        time.sleep(0.5)

        if double_click:
            mouse_click("left")
            time.sleep(0.1)
            mouse_click("left")
            logger.info(f"Double-clicked element at ({center_x}, {center_y}): {selector}")
            return (
                f"Double-clicked element: {selector}\n"
                f"{_get_feedback_state()}"
            )
        else:
            mouse_click("left")
            logger.info(f"Clicked element at ({center_x}, {center_y}): {selector}")
            return (
                f"Clicked element: {selector}\n"
                f"{_get_feedback_state()}"
            )
    except Exception as e:
        logger.error(f"Error clicking element {selector}: {str(e)}")
        return f"Error clicking element: {str(e)}"
