import random
import time
import asyncio
import pyautogui
import pygetwindow as gw
from llama_index.core.tools import FunctionTool
from agent.self_correcting_vision_agent_4 import SelfCorrectingVisionAgentV4
from constants.allowed_hotkeys import ALLOWED_HOTKEYS
from typing import List, Optional

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
vision_agent = SelfCorrectingVisionAgentV4()

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
        vision_agent.clear_thought_process()
        terminal_pos = _hide_terminal()
        time.sleep(0.3)
        response = vision_agent.analyze_current_screen(prompt)
        print(f"DEBUG: Vision agent returned: {response[:500] if response else 'None'}")
        
        thoughts = vision_agent.get_thought_process()
        if thoughts:
            thought_log = "\n".join(f"  [{i+1}] {t}" for i, t in enumerate(thoughts))
            print(f"DEBUG: Agent thought process:\n{thought_log}")
            return f"Vision Analysis Result:\n{response}\n\nAgent Thought Process:\n{thought_log}"
        return f"Vision Analysis Result:\n{response}"
    except Exception as e:
        print(f"ERROR: Failed to analyze screen: {type(e).__name__}: {str(e)}")
        print(f"ERROR: Full traceback:\n{traceback.format_exc()}")
        return f"Failed to analyze screen: {str(e)}"
    finally:
        if terminal_pos:
            _show_terminal(terminal_pos)


def drag_mouse(prompt: str, keys: Optional[List[str]] = None) -> str:
    """
    Moves the mouse cursor to the target GUI element specified in prompt,
    optionally holding down the specified keys/buttons during the movement.
    When no keys are provided, this acts as a simple move operation.
    This enables drag operations like left-click drag, right-click drag,
    right-click + shift drag, etc.

    The vision agent handles the mouse movement internally. This function
    simply presses the specified keys before calling locate_element, then
    releases them afterward.

    Args:
        prompt: Description of the target GUI element to drag to.
                Be precise and concise (e.g., "wifi icon located at the right of the bottom toolbar").
        keys: Optional list of keys/buttons to press simultaneously during the drag.
              Mouse buttons: "left", "right", "middle"
              Keyboard keys: any valid key name (e.g., "ctrl", "shift", "alt")
              Examples: ["left"], ["right"], ["ctrl", "left"], ["shift", "right"]
              When None or empty, acts as a simple mouse move.

    Returns:
        A string with the vision agent result and drag confirmation.

    For example, to left-click drag to a target:
        drag_mouse(prompt="the save button", keys=["left"])

    To right-click drag with shift held:
        drag_mouse(prompt="the delete option", keys=["right", "shift"])

    To simply move the mouse (no drag):
        drag_mouse(prompt="the save button")
    """
    import traceback

    print(f"DEBUG: Tool called with prompt: {prompt}, keys: {keys}")
    terminal_pos = None

    MOUSE_BUTTONS = {"left", "right", "middle"}

    try:
        terminal_pos = _hide_terminal()
        time.sleep(0.3)

        # Separate mouse buttons from keyboard keys
        mouse_buttons = [k for k in keys if k.lower() in MOUSE_BUTTONS] if keys else []
        keyboard_keys = [k for k in keys if k.lower() not in MOUSE_BUTTONS] if keys else []

        # Press all mouse buttons and keyboard keys down
        for mb in mouse_buttons:
            pyautogui.mouseDown(button=mb.lower())
        for k in keyboard_keys:
            pyautogui.keyDown(k.lower())

        try:
            # Get target coordinates from the vision agent
            # This moves the mouse to the target position with smooth animation
            vision_agent.clear_thought_process()
            result = vision_agent.locate_element(prompt)
            print(f"DEBUG: Vision agent returned: {result}")
            target_x, target_y = result.x, result.y
            
            thoughts = vision_agent.get_thought_process()
            thought_log = ""
            if thoughts:
                thought_log = "\n".join(f"  [{i+1}] {t}" for i, t in enumerate(thoughts))
                print(f"DEBUG: Agent thought process:\n{thought_log}")
            
            drag_info = f"Vision Agent Result:\n{result}\nDrag completed to ({target_x}, {target_y}) with keys: {keys}"
            if thought_log:
                drag_info += f"\n\nAgent Thought Process:\n{thought_log}"
            return drag_info
        finally:
            # Release all keys/buttons in reverse order
            for mb in reversed(mouse_buttons):
                pyautogui.mouseUp(button=mb.lower())
            for k in reversed(keyboard_keys):
                pyautogui.keyUp(k.lower())

    except Exception as e:
        print(f"ERROR: Failed to drag: {type(e).__name__}: {str(e)}")
        print(f"ERROR: Full traceback:\n{traceback.format_exc()}")
        return f"Failed to drag: {str(e)}"

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
    FunctionTool.from_defaults(fn=left_click),
    FunctionTool.from_defaults(fn=right_click),
    FunctionTool.from_defaults(fn=double_click, async_callback=delay_callback),
    FunctionTool.from_defaults(fn=type_text),
    FunctionTool.from_defaults(fn=press_key, async_callback=delay_callback),
    FunctionTool.from_defaults(fn=execute_hotkey, async_callback=delay_callback),
    FunctionTool.from_defaults(fn=drag_mouse),
]