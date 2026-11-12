"""Get element at screen coordinates."""

from langchain_core.tools import tool
import json

from gui_agent.windows.uia.locator import get_control_from_point
from gui_agent.windows.uia.patterns import get_element_info


@tool
def get_element_at_point(x: int, y: int) -> str:
    """Get element at screen coordinates.

    Args:
        x: Screen X coordinate
        y: Screen Y coordinate

    Returns:
        Element info as JSON string or error message
    """
    try:
        element = get_control_from_point(x, y)
        if element is None:
            return f"No element at ({x}, {y})"

        info = get_element_info(element)
        return json.dumps(info, indent=2)
    except Exception as e:
        return f"Error getting element at point: {str(e)}"