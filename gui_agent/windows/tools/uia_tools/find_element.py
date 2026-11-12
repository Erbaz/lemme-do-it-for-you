"""Find a UI element by selector and return its info."""

from langchain_core.tools import tool
import json

from gui_agent.windows.uia.locator import find_element, get_root
from gui_agent.windows.uia.patterns import get_element_info


@tool
def find_element_tool(selector: str) -> str:
    """Find a UI element by selector and return its info.

    Selector examples:
        - "name:Submit" - Find element with Name="Submit"
        - "class:Button" - Find first Button class element
        - "id:btnLogin" - Find element with AutomationId="btnLogin"

    Args:
        selector: Element selector string

    Returns:
        Element info as JSON string or error message
    """
    try:
        root = get_root()
        element = find_element(root, selector)
        if element is None:
            return f"Element not found: {selector}"

        info = get_element_info(element)
        return json.dumps(info, indent=2)
    except Exception as e:
        return f"Error finding element: {str(e)}"