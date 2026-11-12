"""Get all top-level visible windows on screen."""

from langchain_core.tools import tool
import json
import pythoncom

import uiautomation as auto


def _build_window_selector(element: auto.Control) -> str:
    """Build a selector string for a window element."""
    automation_id = getattr(element, "AutomationId", "")
    name = getattr(element, "Name", "")
    class_name = getattr(element, "ClassName", "")

    if automation_id:
        return f"id:{automation_id}"
    if name:
        return f"name:{name}"
    if class_name:
        return f"class:{class_name}"
    return ""


@tool
def get_top_level_windows(verbose: bool = False) -> str:
    """Get all top-level visible windows on screen (first visual layer).

    Args:
        verbose: If False (default), returns compact summary with name and selector only.
                 If True, returns full details including bounding_rectangle, class_name, automation_id.

    Returns:
        JSON list of window info.
    """
    pythoncom.CoInitialize()
    try:
        windows = []
        desktop = auto.GetRootControl()

        for child in desktop.GetChildren():
            control_type = getattr(child, "ControlTypeName", "")
            if control_type in ("WindowControl", "PaneControl"):
                name = getattr(child, "Name", "")
                class_name = getattr(child, "ClassName", "")
                rect = getattr(child, "BoundingRectangle", None)
                is_visible = getattr(child, "IsOffscreen", True) is False
                is_enabled = getattr(child, "IsEnabled", False)

                if is_visible and is_enabled and name:
                    if verbose:
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

                        windows.append({
                            "name": name,
                            "class_name": class_name,
                            "automation_id": getattr(child, "AutomationId", ""),
                            "control_type": control_type,
                            "bounding_rectangle": rect_info,
                        })
                    else:
                        # Compact summary: just name and selector
                        selector = _build_window_selector(child)
                        if selector:
                            windows.append({
                                "name": name,
                                "selector": selector,
                            })

        return json.dumps(windows, indent=2)
    except Exception as e:
        return f"Error getting top-level windows: {str(e)}"