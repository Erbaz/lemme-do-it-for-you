"""Tool functions for the GUI agent — aggregates test tools and UIA tools."""

from langchain_core.tools import tool
from datetime import datetime

# --- Phase 1 test tools ---

@tool
def echo(text: str) -> str:
    """Echo the input text back."""
    return f"Echo: {text}"


@tool
def get_time() -> str:
    """Get the current date and time."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# --- Phase 2 UIA tools ---
# Each tool is imported from its dedicated module in windows/tools/uia_tools/

from gui_agent.windows.tools.uia_tools import (
    click_element,
    type_text,
    find_element_tool,
    find_elements_tool,
    # mouse_move,  # Temporarily disabled - use click_element instead
    mouse_click,
    press_key,
    read_accessibility_tree,
    get_element_at_point,
    scroll_element,
    expand_element,
    collapse_element,
    get_top_level_windows,
    get_focused_windows,
    get_interactable_elements,
)

__all__ = [
    # Test tools
    "echo",
    "get_time",
    # UIA tools
    "click_element",
    "type_text",
    "find_element_tool",
    "find_elements_tool",
    # "mouse_move",  # Temporarily disabled - use click_element instead
    "mouse_click",
    "press_key",
    "read_accessibility_tree",
    "get_element_at_point",
    "scroll_element",
    "expand_element",
    "collapse_element",
    "get_top_level_windows",
    "get_focused_windows",
    "get_interactable_elements",
    "registry"
]