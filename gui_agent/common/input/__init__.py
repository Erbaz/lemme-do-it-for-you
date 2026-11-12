"""Input package."""
from .mouse import move_mouse, mouse_click, get_mouse_position
from .keyboard import send_keys, send_key

__all__ = ["move_mouse", "mouse_click", "get_mouse_position", "send_keys", "send_key"]
