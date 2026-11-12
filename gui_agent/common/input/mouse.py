"""Mouse input primitives using Windows SendInput API."""

import ctypes
import time
from ctypes import wintypes
from dataclasses import dataclass
from typing import Tuple


# Windows constants
INPUT_MOUSE = 0
MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_ABSOLUTE = 0x8000


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(wintypes.ULONG)),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.DWORD),
        ("mi", MOUSEINPUT),
    ]


def send_input(inputs: list[INPUT]) -> int:
    """Send input events to the system.

    Args:
        inputs: List of INPUT structures to send.

    Returns:
        Number of events successfully sent.
    """
    n_inputs = len(inputs)
    input_array = INPUT * n_inputs
    return ctypes.windll.user32.SendInput(n_inputs, input_array(), ctypes.sizeof(INPUT))


def move_mouse(x: int, y: int) -> bool:
    """Move mouse cursor to absolute screen coordinates.

    Args:
        x: Screen X coordinate in pixels.
        y: Screen Y coordinate in pixels.

    Returns:
        True if successful.
    """
    result = ctypes.windll.user32.SetCursorPos(x, y)
    return result != 0


def mouse_click(button: str = "left") -> bool:
    """Perform a mouse click at the current cursor position.

    Uses mouse_event with MOUSEEVENTF_ABSOLUTE and current cursor
    coordinates to ensure Windows processes it as a real input event.

    Args:
        button: Button to click ('left' or 'right').

    Returns:
        True if successful.
    """
    x, y = get_mouse_position()

    # Normalize to 0-65535 range for MOUSEEVENTF_ABSOLUTE
    screen_width = ctypes.windll.user32.GetSystemMetrics(0)
    screen_height = ctypes.windll.user32.GetSystemMetrics(1)
    norm_x = int((x / screen_width) * 65535)
    norm_y = int((y / screen_height) * 65535)

    if button == "left":
        down_flag = MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_ABSOLUTE
        up_flag = MOUSEEVENTF_LEFTUP | MOUSEEVENTF_ABSOLUTE
    elif button == "right":
        down_flag = MOUSEEVENTF_RIGHTDOWN | MOUSEEVENTF_ABSOLUTE
        up_flag = MOUSEEVENTF_RIGHTUP | MOUSEEVENTF_ABSOLUTE
    else:
        raise ValueError(f"Unknown button: {button}")

    ctypes.windll.user32.mouse_event(down_flag, norm_x, norm_y, 0, 0)
    time.sleep(0.05)
    ctypes.windll.user32.mouse_event(up_flag, norm_x, norm_y, 0, 0)
    return True


def get_mouse_position() -> Tuple[int, int]:
    """Get current mouse cursor position.

    Returns:
        Tuple of (x, y) screen coordinates.
    """
    class POINT(ctypes.Structure):
        _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]

    point = POINT()
    ctypes.windll.user32.GetCursorPos(ctypes.byref(point))
    return (point.x, point.y)