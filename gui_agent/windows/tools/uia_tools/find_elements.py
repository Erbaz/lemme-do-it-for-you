"""Find all UI elements matching selector and return their info."""

from langchain_core.tools import tool
import json

from gui_agent.windows.uia.locator import find_elements, get_root
from gui_agent.windows.uia.patterns import get_element_info
from gui_agent.common.selector_tracker import selector_tracker


@tool
def find_elements_tool(selector: str) -> str:
    """Find all UI elements matching selector and return their info.

    Selector examples:
        - "class:Button" - Find all Button elements
        - "name:Item" - Find all elements with Name="Item"

    Args:
        selector: Element selector string

    Returns:
        List of element info as JSON string or error message
    """
    if selector_tracker.is_failed(selector):
        return f"Selector previously failed: {selector}"

    try:
        root = get_root()
        elements = find_elements(root, selector)
        if not elements:
            selector_tracker.record_failure(selector)
            return f"No elements found: {selector}"

        results = [get_element_info(el) for el in elements]
        return json.dumps(results, indent=2)
    except Exception as e:
        return f"Error finding elements: {str(e)}"
