"""Collapse a tree item, combo box, or other collapsible element."""

from langchain_core.tools import tool

from gui_agent.windows.uia.locator import find_element, get_root
from gui_agent.windows.uia.patterns import collapse


@tool
def collapse_element(selector: str) -> str:
    """Collapse a tree item, combo box, or other collapsible element.

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

        if collapse(element):
            return f"Collapsed element: {selector}"
        else:
            return f"Failed to collapse element: {selector} (no collapse pattern)"
    except Exception as e:
        return f"Error collapsing element: {str(e)}"