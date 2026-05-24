import os
import pyautogui
from llama_index.core.tools import FunctionTool
from agent.vision_agent import VisionAgent

# Initialize the vision agent globally or lazily
_vision_agent = None

def get_vision_agent():
    global _vision_agent
    if _vision_agent is None:
        _vision_agent = VisionAgent()
    return _vision_agent

def analyze_screen(prompt: str) -> str:
    """
    Takes a screenshot of the current desktop and asks the Vision Agent to analyze it based on the prompt.
    Use this tool whenever you need to find an element's coordinates on the screen or understand the visual state.
    Provide a specific prompt, e.g., 'Find the chrome cross button and provide its x, y coordinates'.
    """
    screenshot_path = "current_screen.png"
    try:
        # Take screenshot
        pyautogui.screenshot(screenshot_path)
        
        # Analyze using Vision Agent
        vision_agent = get_vision_agent()
        response = vision_agent.analyze(prompt, screenshot_path)
        
        return f"Vision Analysis Result:\n{response}"
    except Exception as e:
        return f"Failed to analyze screen: {str(e)}"

def move_mouse(x: int, y: int) -> str:
    """
    Moves the mouse cursor to the absolute x, y coordinates on the screen.
    """
    try:
        pyautogui.moveTo(x, y)
        return f"Mouse moved to ({x}, {y})"
    except Exception as e:
        return f"Failed to move mouse: {str(e)}"

def left_click() -> str:
    """
    Performs a single left mouse click at the current cursor position.
    """
    try:
        pyautogui.click()
        return "Left clicked."
    except Exception as e:
        return f"Failed to left click: {str(e)}"

def right_click() -> str:
    """
    Performs a single right mouse click at the current cursor position.
    """
    try:
        pyautogui.rightClick()
        return "Right clicked."
    except Exception as e:
        return f"Failed to right click: {str(e)}"

def double_click() -> str:
    """
    Performs a double left mouse click at the current cursor position.
    """
    try:
        pyautogui.doubleClick()
        return "Double clicked."
    except Exception as e:
        return f"Failed to double click: {str(e)}"

def type_text(text: str) -> str:
    """
    Types the specified text string using the keyboard.
    """
    try:
        pyautogui.write(text, interval=0.05)
        return f"Typed: '{text}'"
    except Exception as e:
        return f"Failed to type text: {str(e)}"

def press_key(key: str) -> str:
    """
    Presses a specific keyboard key (e.g., 'enter', 'tab', 'esc', 'win').
    """
    try:
        pyautogui.press(key)
        return f"Pressed key: '{key}'"
    except Exception as e:
        return f"Failed to press key: {str(e)}"

def get_all_tools() -> list[FunctionTool]:
    """
    Returns a list of all FunctionTools available for the ReAct Agent.
    """
    return [
        FunctionTool.from_defaults(fn=analyze_screen),
        FunctionTool.from_defaults(fn=move_mouse),
        FunctionTool.from_defaults(fn=left_click),
        FunctionTool.from_defaults(fn=right_click),
        FunctionTool.from_defaults(fn=double_click),
        FunctionTool.from_defaults(fn=type_text),
        FunctionTool.from_defaults(fn=press_key),
    ]
