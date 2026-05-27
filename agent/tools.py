import random
import time
import pyautogui
from llama_index.core.tools import FunctionTool
from agent.self_correcting_vision_agent import SelfCorrectingVisionAgent


# Initialize the vision agent globally or lazily
vision_agent = SelfCorrectingVisionAgent()

def analyze_screen(prompt: str) -> str:
    """
    Takes a screenshot of the current desktop and asks the Vision Agent to analyze it based on the prompt.
    Use this tool to get context of the current screen state to help you understand and build towards next actions.
    In prompt, ask the vision agent directly what you want it to describe such as open windows, apps, browser tabs etc, that will help you figure out next steps.
    Do not bother with explaining, be direct in the prompt.
    """
    print(f"DEBUG: Tool called with prompt: {prompt}")
    try:
        # Analyze using Vision Agent
        
        response = vision_agent.analyze_current_screen(prompt)
        
        return f"Vision Analysis Result:\n{response}"
    except Exception as e:
        print(f"Failed to analyze screen: {str(e)}")
        return f"Failed to analyze screen: {str(e)}"


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
    
    try:
        response = vision_agent.locate_element(prompt)

        return f"Vision Agent Result:\n{response}"
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

def execute_hotkey(command: str) -> str:
        """
        Executes an allowed keyboard shortcut. 
        Supported commands: 'save', 'copy', 'paste', 'refresh'.
        """
        whitelist = {
            "save": ["ctrl", "s"],
            "copy": ["ctrl", "c"],
            "paste": ["ctrl", "v"],
            "refresh": ["f5"]
        }
        if command not in whitelist:
            return f"Error: Command '{command}' is not in the whitelist. Only {', '.join(whitelist.keys())} are allowed."
        
        keys = whitelist[command]
        pyautogui.hotkey(*keys)
        return f"Successfully executed {command} ({'+'.join(keys)})"


agent_tools = [
    FunctionTool.from_defaults(fn=analyze_screen),
    FunctionTool.from_defaults(fn=move_mouse),
    FunctionTool.from_defaults(fn=left_click),
    FunctionTool.from_defaults(fn=right_click),
    FunctionTool.from_defaults(fn=double_click),
    FunctionTool.from_defaults(fn=type_text),
    FunctionTool.from_defaults(fn=press_key),
    FunctionTool.from_defaults(fn=execute_hotkey)
]