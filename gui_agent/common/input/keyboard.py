"""Keyboard input primitives using uiautomation."""

import uiautomation as auto


def send_keys(text: str, interval: float = 0.0) -> bool:
    """Send keystrokes to the active window.

    Args:
        text: Text to type.
        interval: Delay between keystrokes in seconds.

    Returns:
        True if successful.
    """
    try:
        auto.SendKeys(text, interval=interval)
        return True
    except Exception:
        return False


def send_key(key: str) -> bool:
    """Send a single special key.

    Args:
        key: Key name (e.g., '{ENTER}', '{TAB}', '{ESC}').

    Returns:
        True if successful.
    """
    try:
        auto.SendKeys(key)
        return True
    except Exception:
        return False