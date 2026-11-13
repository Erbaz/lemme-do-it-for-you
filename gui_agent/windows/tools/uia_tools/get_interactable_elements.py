"""Get all mouse-interactable elements on screen."""

from langchain_core.tools import tool
import json
import pythoncom

import uiautomation as auto

# Control types that are typically clickable or typeable
INTERACTABLE_TYPES = {
    "ButtonControl",
    "EditControl",
    "HyperlinkControl",
    "MenuItemControl",
    "ListItemControl",
    "TreeItemControl",
    "TabItemControl",
    "CheckBoxControl",
    "RadioButtonControl",
    "SliderControl",
    "SpinnerControl",
    "ComboBoxControl",
    "SplitButtonControl",
    "DataItemControl",
}


def _is_mouse_interactable(element: auto.Control) -> bool:
    """Check if an element is mouse-interactable."""
    try:
        rect = getattr(element, "BoundingRectangle", None)
        if rect is None:
            return False

        control_type = getattr(element, "ControlTypeName", "")
        name = getattr(element, "Name", "")
        automation_id = getattr(element, "AutomationId", "")

        # Must be visible, enabled, on-screen, and have a clickable area
        if getattr(element, "IsOffscreen", True):
            return False
        if not getattr(element, "IsEnabled", False):
            return False
        if rect.width() <= 0 or rect.height() <= 0:
            return False
        if rect.left < 0 or rect.top < 0:
            return False

        # Must be an interactable control type OR have a name/automation_id
        if control_type in INTERACTABLE_TYPES:
            return True
        if name or automation_id:
            # Could still be clickable (e.g., custom controls)
            return True

        return False
    except Exception:
        return False


def _build_selector(element: auto.Control) -> str:
    """Build a selector string for an element."""
    name = getattr(element, "Name", "")
    class_name = getattr(element, "ClassName", "")
    automation_id = getattr(element, "AutomationId", "")

    if automation_id:
        return f"id:{automation_id}"
    if name:
        return f"name:{name}"
    if class_name:
        return f"class:{class_name}"
    return ""


def _collect_interactable(control: auto.Control, results: list, max_depth: int = 5, current_depth: int = 1, verbose: bool = False):
    """Recursively collect all mouse-interactable elements."""
    if current_depth > max_depth:
        return

    try:
        for child in control.GetChildren():
            if _is_mouse_interactable(child):
                if verbose:
                    rect = getattr(child, "BoundingRectangle", None)
                    rect_info = None
                    if rect:
                        rect_info = {
                            "left": rect.left,
                            "top": rect.top,
                            "right": rect.right,
                            "bottom": rect.bottom,
                            "width": rect.width(),
                            "height": rect.height(),
                        }

                    results.append({
                        "name": getattr(child, "Name", ""),
                        "class_name": getattr(child, "ClassName", ""),
                        "automation_id": getattr(child, "AutomationId", ""),
                        "control_type": getattr(child, "ControlTypeName", ""),
                        "bounding_rectangle": rect_info,
                        "selector": _build_selector(child),
                    })
                else:
                    # Compact summary: just name, selector, and control_type
                    selector = _build_selector(child)
                    if selector:
                        results.append({
                            "name": getattr(child, "Name", ""),
                            "selector": selector,
                            "control_type": getattr(child, "ControlTypeName", ""),
                        })

            # Recurse into children
            _collect_interactable(child, results, max_depth, current_depth + 1, verbose)
    except Exception:
        pass


@tool
def get_interactable_elements(max_depth: int = 3, scope: str = "all", verbose: bool = False) -> str:
    """Get all mouse-clickable/typeable elements on screen.

    Use this to find clickable targets (buttons, edits, list items, etc.)
    within a specific scope. Returns selectors you can pass directly to
    click_element() or type_text().

    Args:
        max_depth: Maximum tree depth to traverse (default 3)
        scope: "foreground" (focused window only) | "all_windows" | "desktop" (default: "all")
        verbose: If False (default), returns compact summary with name, selector, and control_type only.
                 If True, returns full details including bounding_rectangle, class_name, automation_id.

    Returns:
        JSON list of interactable elements with selectors for direct tool use
    """
    try:
        results = []

        pythoncom.CoInitialize()

        if scope == "foreground":
            focused = auto.GetFocusedControl()
            if focused:
                # Walk up to find top-level window
                window = focused
                while window:
                    parent = window.GetParentControl()
                    if parent is None:
                        break
                    window = parent
                _collect_interactable(window, results, max_depth, verbose=verbose)
        elif scope == "all_windows":
            desktop = auto.GetRootControl()
            for child in desktop.GetChildren():
                control_type = getattr(child, "ControlTypeName", "")
                if control_type in ("WindowControl", "PaneControl"):
                    _collect_interactable(child, results, max_depth, verbose=verbose)
        else:  # desktop
            desktop = auto.GetRootControl()
            _collect_interactable(desktop, results, max_depth, verbose=verbose)

        return json.dumps(results, indent=2)
    except Exception as e:
        return f"Error getting interactable elements: {str(e)}"

