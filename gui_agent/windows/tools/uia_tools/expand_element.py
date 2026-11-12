"""Expand a tree item, combo box, or other expandable element."""

from langchain_core.tools import tool

from gui_agent.windows.uia.locator import find_element, get_root
from gui_agent.windows.uia.patterns import expand


@tool
def expand_element(selector: str) -> str:
    """Expand a tree item, combo box, or other expandable element.

    Args:
        selector: Element selector string

    Returns:
        Success or error message
    """
    try:
        root = get_root()
        element = find_element(root, selector)
        if element is None:
            return f"Element not found: {selector}"

        if expand(element):
            return f"Expanded element: {selector}"
        else:
            return f"Failed to expand element: {selector} (no expand pattern)"
    except Exception as e:
        return f"Error expanding element: {str(e)}"