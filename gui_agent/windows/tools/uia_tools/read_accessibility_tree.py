"""Read the accessibility tree starting from root or a specific element.

    Use this ONLY when you need to understand a specific window's internal UI hierarchy.
    Do not use this for general discovery — use get_interactable_elements() or get_top_level_windows() instead."""

from langchain_core.tools import tool
import json

import uiautomation as auto

from gui_agent.windows.uia.locator import find_element, get_root
from gui_agent.windows.uia.patterns import get_element_info


def _build_tree(element: auto.Control, current_depth: int, max_depth: int, verbose: bool = False) -> dict:
    if current_depth > max_depth:
        return {}

    if verbose:
        info = get_element_info(element)
    else:
        # Compact summary: just name, selector, and control_type
        from gui_agent.windows.uia.locator import build_selector
        info = {
            "name": getattr(element, "Name", ""),
            "selector": build_selector(element),
            "control_type": getattr(element, "ControlTypeName", ""),
        }
        # Only include non-empty fields
        info = {k: v for k, v in info.items() if v}

    children = []
    try:
        for child in element.GetChildren():
            child_info = _build_tree(child, current_depth + 1, max_depth, verbose)
            if child_info:
                children.append(child_info)
    except Exception:
        pass

    if children:
        info["children"] = children
    return info


@tool
def read_accessibility_tree(depth: int = 3, selector: str = "", verbose: bool = False) -> str:
    """Read the accessibility tree starting from root or a specific element.

    Args:
        depth: Maximum depth to traverse (default 3)
        selector: Optional selector to start from specific element
        verbose: If False (default), returns compact summary with name, selector, and control_type only.
                 If True, returns full details including bounding_rectangle, class_name, automation_id, value, etc.

    Returns:
        Tree structure as JSON string
    """

    try:
        if selector:
            root = get_root()
            start_element = find_element(root, selector)
            if start_element is None:
                return f"Start element not found: {selector}"
        else:
            start_element = get_root()

        tree = _build_tree(start_element, 1, depth, verbose)
        return json.dumps(tree, indent=2)
    except Exception as e:
        return f"Error reading accessibility tree: {str(e)}"