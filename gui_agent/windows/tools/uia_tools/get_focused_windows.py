"""Get currently focused/foreground windows on screen."""

from langchain_core.tools import tool
import json
import pythoncom

import uiautomation as auto


@tool
def get_focused_windows() -> str:
    """Get currently focused/foreground window(s) on screen.

    Returns:
        JSON list of focused window info
    """
    pythoncom.CoInitialize()
    try:
        windows = []
        focused = auto.GetFocusedControl()

        if focused:
            # Walk up to find the top-level WindowControl containing the focused control.
            # Stop at WindowControl (e.g., VSCode, Windows Terminal) instead of going
            # all the way up to Desktop 1.
            window = focused
            while window:
                control_type = getattr(window, "ControlTypeName", "")
                if control_type == "WindowControl":
                    break
                parent = window.GetParentControl()
                if parent is None:
                    break
                window = parent

            if window:
                name = getattr(window, "Name", "")
                class_name = getattr(window, "ClassName", "")
                rect = getattr(window, "BoundingRectangle", None)
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
                    "automation_id": getattr(window, "AutomationId", ""),
                    "control_type": getattr(window, "ControlTypeName", ""),
                    "bounding_rectangle": rect_info,
                    "focused_control_name": getattr(focused, "Name", ""),
                    "focused_control_class": getattr(focused, "ClassName", ""),
                })

        return json.dumps(windows, indent=2)
    except Exception as e:
        return f"Error getting focused windows: {str(e)}"