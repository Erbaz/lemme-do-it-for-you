"""The identity record attached to every recorded element.

``gui_agent``'s own element info has no PID and no ``IsPassword``; this is the
scriber's own snapshot of the element under the cursor.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Tuple

#: Control types that are interactive; used to prefer the button over its icon.
INTERACTIVE_TYPES = frozenset({
    "ButtonControl", "SplitButtonControl", "EditControl", "ComboBoxControl",
    "MenuItemControl", "TabItemControl", "ListItemControl", "TreeItemControl",
    "DataItemControl", "CheckBoxControl", "RadioButtonControl",
    "HyperlinkControl", "SliderControl", "SpinnerControl",
})

#: Unicode Private Use Areas. A name made of these is an icon font, not a label.
PRIVATE_USE_RANGES = (
    (0xE000, 0xF8FF),
    (0xF0000, 0xFFFFD),
    (0x100000, 0x100FFFD),
)

#: Class strings longer than this are framework class lists, not identifiers.
MAX_CLASS_LEN = 40


def _has_private_use(text: str) -> bool:
    for ch in text:
        code = ord(ch)
        for low, high in PRIVATE_USE_RANGES:
            if low <= code <= high:
                return True
    return False


def _selector_safe(value: str) -> bool:
    """Can the value survive ``parse_selector`` unchanged?"""
    return (
        bool(value)
        and value == value.strip()
        and "," not in value
        and not _has_private_use(value)
    )


def _usable_class(class_name: str) -> bool:
    return (
        _selector_safe(class_name)
        and len(class_name) <= MAX_CLASS_LEN
        and " " not in class_name
    )


def candidate_selectors(fp: "Fingerprint") -> List[str]:
    """Every selector likely to resolve to this element, best first."""
    out: List[str] = []
    if _selector_safe(fp.automation_id):
        out.append(f"id:{fp.automation_id}")
    if _selector_safe(fp.name):
        out.append(f"name:{fp.name}")
        if _usable_class(fp.class_name):
            out.append(f"name:{fp.name},class:{fp.class_name}")
    if _usable_class(fp.class_name):
        out.append(f"class:{fp.class_name}")
    return list(dict.fromkeys(out))


@dataclass(frozen=True)
class Fingerprint:
    """The properties that identify one UI element."""

    control_type: str
    name: str
    automation_id: str
    class_name: str
    rect: Tuple[int, int, int, int]
    pid: int
    is_password: bool

    def to_dict(self) -> Dict[str, Any]:
        return {
            "control_type": self.control_type,
            "name": self.name,
            "automation_id": self.automation_id,
            "class_name": self.class_name,
            "rect": {
                "left": self.rect[0],
                "top": self.rect[1],
                "right": self.rect[2],
                "bottom": self.rect[3],
            },
            "pid": self.pid,
            "is_password": self.is_password,
        }


__all__ = ["Fingerprint", "INTERACTIVE_TYPES", "candidate_selectors"]
