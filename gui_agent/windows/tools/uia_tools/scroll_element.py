"""Scroll a scrollable element."""

from langchain_core.tools import tool

from gui_agent.windows.uia.locator import find_element, get_root
from gui_agent.windows.uia.patterns import scroll


@tool
def scroll_element(selector: str, direction: str, amount: str = "small") -> str:
    """Scroll a scrollable element.

    Args:
        selector: Element selector string
        direction: "up", "down", "left", or "right"
        amount: "small", "large", or "page" (default: "small")

    Returns:
        Success or error message
    """
    try:
        root = get_root()
        element = find_element(root, selector)
        if element is None:
            return f"Element not found: {selector}"

        if scroll(element, direction, amount):
            return f"Scrolled {selector} {direction} ({amount})"
        else:
            return f"Failed to scroll {selector} (no scroll pattern)"
    except Exception as e:
        return f"Error scrolling element: {str(e)}"