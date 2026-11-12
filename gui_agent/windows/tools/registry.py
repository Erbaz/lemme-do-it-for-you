from gui_agent.tools import (
    echo,
    get_time,
    click_element,
    type_text,
    find_element_tool,
    find_elements_tool,
    # mouse_move,  # Temporarily disabled - use click_element instead
    read_accessibility_tree,
    get_focused_element_info,
    get_element_at_point,
    scroll_element,
    expand_element,
    collapse_element,
    get_top_level_windows,
    get_focused_windows,
    get_interactable_elements,
)


TOOL_REGISTRY = [
        echo,
        get_time,
        click_element,
        type_text,
        find_element_tool,
        find_elements_tool,
        # mouse_move,  # Temporarily disabled - use click_element instead
        read_accessibility_tree,
        get_focused_element_info,
        get_element_at_point,
        scroll_element,
        expand_element,
        collapse_element,
        get_top_level_windows,
        get_focused_windows,
        get_interactable_elements,
]