import random
import time
import asyncio
import pyautogui
import pygetwindow as gw
from llama_index.core.tools import FunctionTool
from agent.self_correcting_vision_agent_3 import SelfCorrectingVisionAgentV3
from constants.allowed_hotkeys import ALLOWED_HOTKEYS
from typing import List

TERMINAL_TITLE = "MyHiddenTerminal"


def _hide_terminal():
    """Find and hide the stealth terminal by title. Returns original position or None."""
    windows = gw.getWindowsWithTitle(TERMINAL_TITLE)
    if windows:
        win = windows[0]
        try:
            pos = (win.left, win.top)
            win.moveTo(-2000, -2000)
            return pos
        except Exception:
            return None
    return None


def _show_terminal(pos):
    """Restore the stealth terminal to its original position."""
    if not pos:
        return
    windows = gw.getWindowsWithTitle(TERMINAL_TITLE)
    if windows:
        try:
            windows[0].moveTo(*pos)
        except Exception:
            pass


# Initialize the vision agent globally or lazily
vision_agent = SelfCorrectingVisionAgentV3()

def analyze_screen(prompt: str) -> str:
    """
    Takes a screenshot of the current desktop and asks the Vision Agent to analyze it based on the prompt.
    Use this tool to get context of the current screen state to help you understand and build towards next actions.
    In prompt, ask the vision agent directly what you want it to describe such as open windows, apps, browser tabs etc, that will help you figure out next steps.
    Do not bother with explaining, be direct in the prompt.
    """
    import traceback
    print(f"DEBUG: Tool called with prompt: {prompt}")
    terminal_pos = None
    try:
        terminal_pos = _hide_terminal()
        time.sleep(0.3)
        response = vision_agent.analyze_current_screen(prompt)
        print(f"DEBUG: Vision agent returned: {response[:500] if response else 'None'}")
        return f"Vision Analysis Result:\n{response}"
    except Exception as e:
        print(f"ERROR: Failed to analyze screen: {type(e).__name__}: {str(e)}")
        print(f"ERROR: Full traceback:\n{traceback.format_exc()}")
        return f"Failed to analyze screen: {str(e)}"
    finally:
        if terminal_pos:
            _show_terminal(terminal_pos)


def move_mouse(prompt: str) -> str:
    """
    Takes the targetted GUI element on screen in prompt and gives it to the vision agent to move mouse cursor to it's postion.
    The vision agent will try to move the mouse to the desired GUI object / element so make sure to describe precisely and concisely the target.
    For example, if you wish to move the mouse to a form field, say: "form field with label username".
    If the vision agent is successful, it will output a json object structure that looks like:
    {"target": "<target>", "x": <x>, "y": <y>, "confidence": "<confidence>", "iterations": <iterations>}
    Do not bother with explaining, be direct in the prompt. Only identify the target with a description if needed. Do not use filler words.
    If the confidence in response is low, you must call this tool with a better prompt
    """
    import traceback
    print(f"DEBUG: Tool called with prompt: {prompt}")
    terminal_pos = None
    try:
        terminal_pos = _hide_terminal()
        time.sleep(0.3)
        response = vision_agent.locate_element(prompt)
        print(f"DEBUG: Vision agent returned: {response}")
        return f"Vision Agent Result:\n{response}"
    except Exception as e:
        print(f"ERROR: Failed to move mouse: {type(e).__name__}: {str(e)}")
        print(f"ERROR: Full traceback:\n{traceback.format_exc()}")
        return f"Failed to move mouse: {str(e)}"
    finally:
        if terminal_pos:
            _show_terminal(terminal_pos)

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
    Types the specified text string using the keyboard. Humanness added
    """
    try:
       
        for char in text:
            # Base interval + random variance
            # This creates a range of 0.05 to 0.15 seconds per character
            delay = random.uniform(0.05, 0.15)
            
            # Occasionally simulate a "burst" of speed or a "hesitation"
            if random.random() < 0.1:  # 10% chance to pause longer (e.g., thinking)
                time.sleep(random.uniform(0.3, 0.8))
            
            pyautogui.write(char)
            time.sleep(delay)

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


def execute_hotkey(keys: List[str]) -> str:
    """
    Executes a keyboard hotkey by combining the provided keys.
    
    Args:
        keys: A list of keys to press simultaneously. 
              Examples: ["ctrl", "c"], ["alt", "tab"], ["f5"]
    
    Returns:
        A message confirming the hotkey execution or an error.
    """
    
    # Validate input
    if not isinstance(keys, list) or not keys:
        return "Error: 'keys' must be a non-empty list of key names."
    
    # Normalize keys
    keys_lower = [k.lower().strip() for k in keys]
    
    # Check if combination is in whitelist
    if keys_lower not in ALLOWED_HOTKEYS:
        return f"Error: Hotkey combination {keys_lower} is not allowed."
    
    try:
        pyautogui.hotkey(*keys_lower)
        return f"Successfully executed hotkey: {'+'.join(keys_lower)}"
    except Exception as e:
        return f"Error executing hotkey: {str(e)}"


async def delay_callback(_tool=None):
    await asyncio.sleep(3)
    return None


agent_tools = [
    FunctionTool.from_defaults(fn=analyze_screen),
    FunctionTool.from_defaults(fn=move_mouse),
    FunctionTool.from_defaults(fn=left_click),
    FunctionTool.from_defaults(fn=right_click),
    FunctionTool.from_defaults(fn=double_click, async_callback=delay_callback),
    FunctionTool.from_defaults(fn=type_text),
    FunctionTool.from_defaults(fn=press_key, async_callback=delay_callback),
    FunctionTool.from_defaults(fn=execute_hotkey, async_callback=delay_callback)
]