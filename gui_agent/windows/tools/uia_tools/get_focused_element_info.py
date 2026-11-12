"""Get info about the currently focused element."""

from langchain_core.tools import tool
import json

from gui_agent.windows.uia.locator import get_focused_element
from gui_agent.windows.uia.patterns import get_element_info


@tool
def get_focused_element_info() -> str:
    """Get info about the currently focused element.

    Returns:
        Element info as JSON string or error message
    """
    try:
        element = get_focused_element()
        if element is None:
            return "No focused element found"

        info = get_element_info(element)
        return json.dumps(info, indent=2)
    except Exception as e:
        return f"Error getting focused element: {str(e)}"