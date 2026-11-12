"""UIA element locator - parses selector strings into uiautomation search criteria."""

import uiautomation as auto
import pythoncom
from typing import Dict, Any, List, Optional, Callable


# Supported selector prefixes
SELECTOR_PREFIXES = {
    "name": "Name",
    "class": "ClassName",
    "id": "AutomationId",
    "automation_id": "AutomationId",
    "control_type": "ControlType",
    "controltype": "ControlType",
    "subname": "SubName",
    "regex": "RegexName",
    "depth": "Depth",
    "xpath": "xpath",
    "index": "index",
}

CONTROL_TYPE_MAP = {
    "button": auto.ButtonControl,
    "edit": auto.EditControl,
    "text": auto.TextControl,
    "combo": auto.ComboBoxControl,
    "combobox": auto.ComboBoxControl,
    "list": auto.ListControl,
    "listitem": auto.ListItemControl,
    "tree": auto.TreeControl,
    "treeitem": auto.TreeItemControl,
    "window": auto.WindowControl,
    "pane": auto.PaneControl,
    "menu": auto.MenuControl,
    "menubar": auto.MenuBarControl,
    "menuitem": auto.MenuItemControl,
    "tab": auto.TabControl,
    "tabitem": auto.TabItemControl,
    "checkbox": auto.CheckBoxControl,
    "radio": auto.RadioButtonControl,
    "slider": auto.SliderControl,
    "spinner": auto.SpinnerControl,
    "scrollbar": auto.ScrollBarControl,
    "statusbar": auto.StatusBarControl,
    "toolbar": auto.ToolBarControl,
    "tooltip": auto.ToolTipControl,
    "hyperlink": auto.HyperlinkControl,
    "image": auto.ImageControl,
    "document": auto.DocumentControl,
    "datagrid": auto.DataGridControl,
    "dataitem": auto.DataItemControl,
    "header": auto.HeaderControl,
    "headeritem": auto.HeaderItemControl,
    "separator": auto.SeparatorControl,
    "thumb": auto.ThumbControl,
    "titlebar": auto.TitleBarControl,
    "calendar": auto.CalendarControl,
    "progress": auto.ProgressBarControl,
    "custom": auto.CustomControl,
    "group": auto.GroupControl,
    "semanticzoom": auto.SemanticZoomControl,
}


def _com_init(func):
    """Decorator to initialize COM for the current thread before calling uiautomation.

    uiautomation requires COM to be initialized on each thread. LangGraph/LangChain
    may run tool functions on separate threads, so we must initialize COM per call.
    We only initialize (never uninitialize) because the control objects returned
    by uiautomation functions need COM to remain alive for the duration of their use.
    COM is cleaned up automatically when the thread exits.
    """
    def wrapper(*args, **kwargs):
        pythoncom.CoInitialize()
        try:
            return func(*args, **kwargs)
        finally:
            pass  # Do not uninitialize - control objects need COM alive
    return wrapper


def parse_selector(selector: str) -> Dict[str, Any]:
    if not selector or not selector.strip():
        raise ValueError("Selector cannot be empty")

    criteria = {}
    parts = [p.strip() for p in selector.split(",") if p.strip()]

    for part in parts:
        if ":" not in part:
            criteria.setdefault("Name", part)
            continue

        prefix, value = part.split(":", 1)
        prefix = prefix.strip().lower()
        value = value.strip()

        if prefix in ("xpath", "index", "type", "control_type", "controltype"):
            criteria[prefix] = value
        elif prefix in SELECTOR_PREFIXES:
            criteria[SELECTOR_PREFIXES[prefix]] = value
        else:
            criteria.setdefault("Name", part)

    return criteria


def _build_control_class(criteria: Dict[str, Any]) -> Callable:
    for key in ("type", "control_type", "controltype"):
        if key in criteria:
            ctrl_type = criteria.pop(key).lower()
            if ctrl_type in CONTROL_TYPE_MAP:
                return CONTROL_TYPE_MAP[ctrl_type]
            for k, v in CONTROL_TYPE_MAP.items():
                if ctrl_type in k or k in ctrl_type:
                    return v
    return auto.Control


def find_element(
    parent: auto.Control,
    selector: str,
    timeout: float = 5.0
) -> Optional[auto.Control]:
    criteria = parse_selector(selector)

    xpath = criteria.pop("xpath", None)
    index = criteria.pop("index", None)

    if xpath:
        return _find_by_xpath(parent, xpath)

    # Use the same tree-walking approach as find_elements for reliability
    elements = find_elements(parent, selector, timeout)

    if not elements:
        return None

    if index is not None:
        try:
            idx = int(index)
            return elements[idx] if 0 <= idx < len(elements) else None
        except ValueError:
            pass

    return elements[0]


@_com_init
def find_elements(
    parent: auto.Control,
    selector: str,
    timeout: float = 5.0
) -> List[auto.Control]:
    criteria = parse_selector(selector)

    xpath = criteria.pop("xpath", None)
    index = criteria.pop("index", None)
    criteria.pop("type", None)
    criteria.pop("control_type", None)
    criteria.pop("controltype", None)

    if xpath:
        result = _find_by_xpath(parent, xpath)
        return [result] if result else []

    control_class = _build_control_class(criteria)

    original_timeout = auto.SetGlobalSearchTimeout(timeout)
    try:
        # Use FindControl with a comparison function
        def compare_fn(ctrl, depth):
            for key, value in criteria.items():
                child_value = getattr(ctrl, key, None)
                if child_value != value:
                    return False
            return True

        results = []
        # Use FindControl in a loop with increasing foundIndex
        found_index = 1
        while True:
            element = auto.FindControl(
                control=parent,
                compare=compare_fn,
                maxDepth=10,
                foundIndex=found_index
            )
            if element is None or not element.Exists(0, 0):
                break
            results.append(element)
            found_index += 1
            if found_index > 100:  # Safety limit
                break

        if index is not None:
            try:
                idx = int(index)
                return [results[idx]] if 0 <= idx < len(results) else []
            except ValueError:
                pass

        return results
    finally:
        auto.SetGlobalSearchTimeout(original_timeout)


def _get_all_descendants(control: auto.Control) -> List[auto.Control]:
    result = []
    try:
        for child in control.GetChildren():
            result.append(child)
            result.extend(_get_all_descendants(child))
    except Exception:
        pass
    return result


@_com_init
def get_root() -> auto.Control:
    return auto.GetRootControl()


@_com_init
def get_focused_element() -> Optional[auto.Control]:
    return auto.GetFocusedControl()


@_com_init
def get_control_from_point(x: int, y: int) -> Optional[auto.Control]:
    return auto.ControlFromPoint(x, y)


def build_selector(element: auto.Control) -> str:
    """Build a selector string from an element's properties."""
    name = getattr(element, "Name", "")
    class_name = getattr(element, "ClassName", "")
    automation_id = getattr(element, "AutomationId", "")

    if automation_id:
        return f"id:{automation_id}"
    if name:
        return f"name:{name}"
    if class_name:
        return f"class:{class_name}"
    return ""


def _find_by_xpath(parent: auto.Control, xpath: str) -> Optional[auto.Control]:
    return None


UIAElement = auto.Control