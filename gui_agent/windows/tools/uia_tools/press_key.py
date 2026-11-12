"""Press a special key (e.g., {ENTER}, {TAB}, {ESC}) on the keyboard."""

from langchain_core.tools import tool

from gui_agent.common.input import send_key


@tool
def press_key(key: str) -> str:
    """Press a special key on the keyboard.

    Useful for pressing {ENTER} after typing into a search box,
    {TAB} to move focus, {ESC} to close a menu, etc.

    Args:
        key: Key name in braces, e.g. "{ENTER}", "{TAB}", "{ESC}", "{SPACE}".

    Returns:
        Success or error message.
    """
    try:
        if send_key(key):
            return f"Pressed key: {key}"
        return f"Failed to press key: {key}"
    except Exception as e:
        return f"Error pressing key: {str(e)}"
