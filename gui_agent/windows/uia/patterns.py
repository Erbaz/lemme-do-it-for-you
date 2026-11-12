"""UIA pattern helpers - thin wrappers around uiautomation pattern objects."""

import uiautomation as auto
from typing import Optional, Literal


def get_invoke_pattern(element: auto.Control) -> Optional[auto.InvokePattern]:
    """Get InvokePattern for clicking/activating an element."""
    try:
        return element.GetInvokePattern()
    except Exception:
        return None


def get_value_pattern(element: auto.Control) -> Optional[auto.ValuePattern]:
    """Get ValuePattern for getting/setting element value."""
    try:
        return element.GetValuePattern()
    except Exception:
        return None


def get_scroll_pattern(element: auto.Control) -> Optional[auto.ScrollPattern]:
    """Get ScrollPattern for scrolling."""
    try:
        return element.GetScrollPattern()
    except Exception:
        return None


def get_expand_collapse_pattern(element: auto.Control) -> Optional[auto.ExpandCollapsePattern]:
    """Get ExpandCollapsePattern for tree items, menus."""
    try:
        return element.GetExpandCollapsePattern()
    except Exception:
        return None


def get_selection_pattern(element: auto.Control) -> Optional[auto.SelectionPattern]:
    """Get SelectionPattern for list/selectable items."""
    try:
        return element.GetSelectionPattern()
    except Exception:
        return None


def get_selection_item_pattern(element: auto.Control) -> Optional[auto.SelectionItemPattern]:
    """Get SelectionItemPattern for individual selectable items."""
    try:
        return element.GetSelectionItemPattern()
    except Exception:
        return None


def get_text_pattern(element: auto.Control) -> Optional[auto.TextPattern]:
    """Get TextPattern for text editing/reading."""
    try:
        return element.GetTextPattern()
    except Exception:
        return None


# --- High-level action helpers ---


def invoke(element: auto.Control) -> bool:
    """Click/activate element using InvokePattern."""
    pattern = get_invoke_pattern(element)
    if pattern:
        try:
            pattern.Invoke()
            return True
        except Exception:
            pass
    return False


def set_value(element: auto.Control, value: str) -> bool:
    """Set element value using ValuePattern."""
    pattern = get_value_pattern(element)
    if pattern:
        try:
            pattern.SetValue(value)
            return True
        except Exception:
            pass
    return False


def get_value(element: auto.Control) -> Optional[str]:
    """Get element value using ValuePattern."""
    pattern = get_value_pattern(element)
    if pattern:
        try:
            return pattern.Value
        except Exception:
            pass
    return None


def scroll(
    element: auto.Control,
    direction: Literal["up", "down", "left", "right"],
    amount: Literal["small", "large", "page"] = "small"
) -> bool:
    """Scroll element in given direction."""
    pattern = get_scroll_pattern(element)
    if not pattern:
        return False

    try:
        horz_map = {"left": auto.ScrollAmount.SmallDecrement, "right": auto.ScrollAmount.SmallIncrement}
        vert_map = {"up": auto.ScrollAmount.SmallDecrement, "down": auto.ScrollAmount.SmallIncrement}

        if amount == "large":
            horz_map = {"left": auto.ScrollAmount.LargeDecrement, "right": auto.ScrollAmount.LargeIncrement}
            vert_map = {"up": auto.ScrollAmount.LargeDecrement, "down": auto.ScrollAmount.LargeIncrement}
        elif amount == "page":
            horz_map = {"left": auto.ScrollAmount.LargeDecrement, "right": auto.ScrollAmount.LargeIncrement}
            vert_map = {"up": auto.ScrollAmount.LargeDecrement, "down": auto.ScrollAmount.LargeIncrement}

        if direction in ("left", "right"):
            pattern.Scroll(horz_map[direction], auto.ScrollAmount.NoAmount)
        else:
            pattern.Scroll(auto.ScrollAmount.NoAmount, vert_map[direction])
        return True
    except Exception:
        return False


def expand(element: auto.Control) -> bool:
    """Expand a tree item or combo box."""
    pattern = get_expand_collapse_pattern(element)
    if pattern:
        try:
            pattern.Expand()
            return True
        except Exception:
            pass
    return False


def collapse(element: auto.Control) -> bool:
    """Collapse a tree item or combo box."""
    pattern = get_expand_collapse_pattern(element)
    if pattern:
        try:
            pattern.Collapse()
            return True
        except Exception:
            pass
    return False


def select_item(element: auto.Control) -> bool:
    """Select an item in a list."""
    pattern = get_selection_item_pattern(element)
    if pattern:
        try:
            pattern.Select()
            return True
        except Exception:
            pass
    return False


def get_bounding_rectangle(element: auto.Control):
    """Get element's bounding rectangle."""
    try:
        return element.BoundingRectangle
    except Exception:
        return None


def double_click_element(element: auto.Control) -> bool:
    """Double-click element - useful for Start Menu items that need activation."""
    rect = get_bounding_rectangle(element)
    if rect:
        from gui_agent.common.input import mouse_click, move_mouse
        center_x = (rect.left + rect.right) // 2
        center_y = (rect.top + rect.bottom) // 2
        move_mouse(center_x, center_y)
        mouse_click("left")
        import time
        time.sleep(0.1)
        return mouse_click("left")
    return False


def type_text(element: auto.Control, text: str) -> bool:
    """Type text into element using ValuePattern or SendKeys.

    Focuses the element first, then types the text literally. No modifier
    keys (e.g. Ctrl+A) are sent — callers that need to clear the field
    should do so explicitly before typing.
    """
    # Try ValuePattern first (fastest, most reliable for Edit controls)
    if set_value(element, text):
        return True

    # Fallback: focus and send keys
    try:
        element.SetFocus()
        from gui_agent.common.input import send_keys
        return send_keys(text)
    except Exception:
        return False


def get_element_text(element: auto.Control) -> str:
    """Get text content of element."""
    # Try Name property first
    name = getattr(element, "Name", None)
    if name:
        return name

    # Try ValuePattern
    value = get_value(element)
    if value:
        return value

    # Try LegacyIAccessible
    legacy = get_legacy_iam_accessible_pattern(element)
    if legacy:
        try:
            return legacy.Value or ""
        except Exception:
            pass

    # Try TextPattern
    text_pattern = get_text_pattern(element)
    if text_pattern:
        try:
            return text_pattern.DocumentRange.GetText(-1)
        except Exception:
            pass

    return ""


def get_element_info(element: auto.Control) -> dict:
    """Get comprehensive element info for debugging."""
    rect = get_bounding_rectangle(element)
    return {
        "name": getattr(element, "Name", ""),
        "class_name": getattr(element, "ClassName", ""),
        "automation_id": getattr(element, "AutomationId", ""),
        "control_type": getattr(element, "ControlTypeName", ""),
        "is_enabled": getattr(element, "IsEnabled", True),
        "is_offscreen": getattr(element, "IsOffscreen", False),
        "bounding_rectangle": {
            "left": rect.left,
            "top": rect.top,
            "right": rect.right,
            "bottom": rect.bottom,
            "width": rect.width(),
            "height": rect.height(),
        } if rect else None,
        "value": get_value(element) or "",
    }