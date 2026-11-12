"""Click mouse at current position."""

from langchain_core.tools import tool

from gui_agent.common.input import mouse_click as do_click


@tool
def mouse_click(button: str = "left") -> str:
    """Click mouse at current position.

    Args:
        button: Mouse button ("left" or "right")

    Returns:
        Success or error message
    """
    try:
        if do_click(button):
            return f"Clicked {button} mouse button"
        else:
            return f"Failed to click {button} mouse button"
    except Exception as e:
        return f"Error clicking mouse: {str(e)}"