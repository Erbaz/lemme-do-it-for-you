import json
import os
import re
import time
from dataclasses import dataclass
from typing import Optional, List, Tuple

import pyautogui
import agent.model  # loads model config from .env and sets Settings.llm
from llama_index.core import Settings
from llama_index.core.base.llms.types import ChatResponse, TextBlock, ThinkingBlock
from llama_index.core.llms import ChatMessage, ImageBlock, MessageRole
from llama_index.llms.ollama import Ollama
from PIL import Image, ImageDraw
import random
import time
import pytweening

# DISABLE FAILSAFE so we can reach corner buttons
pyautogui.FAILSAFE = False 

@dataclass
class LocateResult:
    """Final result of element localization."""
    target: str
    x: int # Native Screen X
    y: int # Native Screen Y
    confidence: str
    iterations: int
    screen_width: int
    screen_height: int

class SelfCorrectingVisionAgent:
    def __init__(
        self,
        model_name: str = "qwen3-vl:4b-instruct",
        context_window: int = 8192,
        request_timeout: float = 300.0,
        max_image_size: int = 1280,
        verbose: bool = True,
    ):
        self.model_name = model_name
        self.max_image_size = max_image_size
        self.verbose = verbose
        self.llm = Settings.llm if Settings.llm else Ollama(
            model=self.model_name,
            request_timeout=request_timeout,
            context_window=context_window,
            options={"num_predict": 1024, "temperature": 0.0},
        )
        # Store failed points in NORMALIZED (0-1000) space
        self.history: List[Tuple[int, int]] = []

    def _log(self, msg: str, level: str = "INFO"):
        if self.verbose:
            print(f"[{time.strftime('%H:%M:%S')}] [{level}] {msg}")

    # ==================== Coordinate Math (The Bridge) ====================

    def _norm_to_native(self, nx, ny):
        sw, sh = pyautogui.size()
        return int((nx / 1000) * sw), int((ny / 1000) * sh)

    def _norm_to_model_img(self, nx, ny, mw, mh):
        return int((nx / 1000) * mw), int((ny / 1000) * mh)


    def _capture_screenshot_with_scaling(self, output_path:str):
        sw, sh = pyautogui.size()
        # Scale for model image
        scale = self.max_image_size / max(sw, sh)
        mw, mh = int(sw * scale), int(sh * scale)
        
        img = pyautogui.screenshot()
        img = img.resize((mw, mh), Image.Resampling.LANCZOS)
        img.save(output_path)

    # ==================== Image Processing ====================

    def capture_processed_screenshot(self, output_path: str, curr_norm: Optional[Tuple[int, int]] = None) -> Tuple[str, int, int]:
        sw, sh = pyautogui.size()
        # Scale for model image
        scale = self.max_image_size / max(sw, sh)
        mw, mh = int(sw * scale), int(sh * scale)
        
        img = pyautogui.screenshot()
        img = img.resize((mw, mh), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(img)

        # 1. Draw History (Blue/Pink)
        colors = ["cyan", "#FF00FF"] 
        for i, pos in enumerate(self.history[:2]):
            hx, hy = self._norm_to_model_img(pos[0], pos[1], mw, mh)
            r = 10
            draw.ellipse([hx-r, hy-r, hx+r, hy+r], fill=colors[i])

        # 2. Draw Current (RED Crosshair)
        if curr_norm:
            cx, cy = self._norm_to_model_img(curr_norm[0], curr_norm[1], mw, mh)
            draw.line([(0, cy), (mw, cy)], fill="red", width=2)
            draw.line([(cx, 0), (cx, mh)], fill="red", width=2)
            r = 20
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline="red", width=2)

        img.save(output_path)
        return output_path, mw, mh

    # ==================== Prompt Methods (Normalized 0-1000) ====================

    def _get_locate_prompt(self, target: str) -> str:
        return f"""You are a computer vision engine. 
Task: Find the exact center coordinates of "{target}".
Use a normalized coordinate system from 0 to 1000, where (0,0) is top-left and (1000,1000) is bottom-right.
Return ONLY JSON: {{"x": <0-1000>, "y": <0-1000>}}"""

    def _get_verify_prompt(self, target: str, nx: int, ny: int) -> str:
        return f"""You are looking at a screenshot. The coordinate system is 0 to 1000.
The RED crosshair is centered exactly at ({nx}, {ny}).

TASK: Is the center of the RED crosshair touching or overlapping the "{target}"?
Return ONLY JSON: {{"confirmed": true or false}}"""

    def _get_offset_prompt(self, target: str, nx: int, ny: int) -> str:
        color_names = ["cyan", "magenta"]
        history_descriptions = []
        for i, pos in enumerate(self.history[:2]):
            color = color_names[i] if i < len(color_names) else f"point_{i+1}"
            history_descriptions.append(f"- {color.upper()} dot was at normalized coordinates ({pos[0]}, {pos[1]})")

        history_text = ""
        if history_descriptions:
            history_text = "\nPrevious attempts shown on image:\n" + "\n".join(history_descriptions) + "\n"

        return f"""You are looking at a screenshot on a 0 to 1000 coordinate scale.
The RED crosshair is currently at normalized coordinates ({nx}, {ny}).
It is NOT on the center of the "{target}".{history_text}
Task: Nudge the RED crosshair. How many units (on a 0-1000 scale) must we move it in X and Y to reach the exact center of "{target}"?
Use the known coordinates of the RED crosshair ({nx}, {ny}) and any previous colored dots above to judge the visual distance and scale.
Return ONLY JSON: {{"offset_x": <int>, "offset_y": <int>}}"""

    # ==================== Main Workflow ====================

    def _chat(self, image_path: str, prompt: str) -> dict:
        msg = [ChatMessage(role=MessageRole.USER, blocks=[ImageBlock(path=image_path), TextBlock(text=prompt)])]

        # Log image details
        try:
            img_size = os.path.getsize(image_path)
            from PIL import Image
            with Image.open(image_path) as img:
                img_format = img.format
                img_mode = img.mode
            self._log(f"Image: {image_path} | Size: {img_size} bytes | Format: {img_format} | Mode: {img_mode}", "DEBUG")
        except Exception as e:
            self._log(f"Could not get image details: {e}", "WARN")

        # Log the prompt
        self._log(f"Sending prompt to LLM: {prompt[:200]}...", "DEBUG")

        response = self.llm.chat(msg)

        # Log raw response details
        self._log(f"LLM Response - Raw: {response}", "DEBUG")
        self._log(f"LLM Response - Message role: {response.message.role}", "DEBUG")
        self._log(f"LLM Response - Number of blocks: {len(response.message.blocks)}", "DEBUG")
        for i, block in enumerate(response.message.blocks):
            block_type = getattr(block, 'block_type', 'unknown')
            block_text = getattr(block, 'text', getattr(block, 'content', 'N/A'))
            self._log(f"LLM Response - Block {i}: type={block_type}, text={str(block_text)[:300]}", "DEBUG")

        content = "".join([b.text if hasattr(b, 'text') else b.content for b in response.message.blocks])
        self._log(f"LLM Response - Combined content: {content}", "DEBUG")

        match = re.search(r"\{[\s\S]*\}", content)
        if not match:
            self._log(f"ERROR: No JSON found in response! Content: {content}", "ERROR")
            raise ValueError(f"No JSON found in LLM response: {content}")
        return json.loads(match.group(0))
    
    
    def _humanly_move_cursor_to(self, target_x, target_y):
        """
        Moves the mouse to (target_x, target_y) using a human-like 
        curved path and variable speed.
        """
        # 1. Get current position
        start_x, start_y = pyautogui.position()
        
        # 2. Define a duration that varies to avoid rhythmic patterns
        duration = random.uniform(0.5, 1.2)
        
        # 3. Create a randomized control point for a Bezier curve
        # This creates a slight arc in the movement path
        mid_x = (start_x + target_x) / 2 + random.randint(-100, 100)
        mid_y = (start_y + target_y) / 2 + random.randint(-100, 100)
        
        # 4. Generate points along a quadratic Bezier curve
        steps = 20
        for i in range(steps + 1):
            t = i / steps
            # Apply easing to simulate acceleration/deceleration
            t = pytweening.easeInOutQuad(t)
            
            # Bezier formula
            curr_x = (1-t)**2 * start_x + 2*(1-t)*t * mid_x + t**2 * target_x
            curr_y = (1-t)**2 * start_y + 2*(1-t)*t * mid_y + t**2 * target_y
            
            # Add tiny bit of jitter to simulate shaky human hands
            jitter_x = random.uniform(-0.5, 0.5)
            jitter_y = random.uniform(-0.5, 0.5)
            
            pyautogui.moveTo(curr_x + jitter_x, curr_y + jitter_y)
            
            # Small sleep between steps to control overall speed
            time.sleep(duration / steps)
    
    def _clear_screenshots(self):
        for file in os.listdir("."):
            if file.endswith(".png"):
                os.remove(file)

    def locate_element(self, target: str, max_iterations: int = 5):
        sw, sh = pyautogui.size()
        self.history = []
        
        # --- Step 0: Absolute Guess ---
        path = "iter_0.png"
        self.capture_processed_screenshot(path)
        data = self._chat(path, self._get_locate_prompt(target))
        curr_nx, curr_ny = int(data["x"]), int(data["y"])
        try:
            for i in range(1, max_iterations + 1):
                # Move Native Mouse
                px, py = self._norm_to_native(curr_nx, curr_ny)
                self._log(f"Iteration {i}: Checking Native ({px}, {py}) | Norm ({curr_nx}, {curr_ny})", "STEP")
                self._humanly_move_cursor_to(px, py)

                # Capture with Markers
                path = f"iter_{i}.png"
                self.capture_processed_screenshot(path, curr_norm=(curr_nx, curr_ny))

                # 1. Verify (Boolean only, no rambling)
                v_data = self._chat(path, self._get_verify_prompt(target, curr_nx, curr_ny))
                if v_data.get("confirmed") is True:
                    self._log("SUCCESS: Confirmed!", "DONE")
                    return LocateResult(target, px, py, "high", i, sw, sh)

                # 2. Get Offset
                self.history.insert(0, (curr_nx, curr_ny))
                if len(self.history) > 3: self.history.pop()
                
                o_data = self._chat(path, self._get_offset_prompt(target, curr_nx, curr_ny))
                curr_nx = max(0, min(1000, curr_nx + int(o_data.get("offset_x", 0))))
                curr_ny = max(0, min(1000, curr_ny + int(o_data.get("offset_y", 0))))

            px, py = self._norm_to_native(curr_nx, curr_ny)
            return LocateResult(target, px, py, "low", max_iterations, sw, sh)
        
        finally:
            self._clear_screenshots()

    def analyze_current_screen(self, prompt:str | None, screenshot_path: str | None = None) -> str:
        self._log(f"prompt from master agent: {prompt}")
        path = screenshot_path or "current_screen.png"
        if not screenshot_path:
            self._capture_screenshot_with_scaling(path)

        # Log image details
        try:
            img_size = os.path.getsize(path)
            from PIL import Image
            with Image.open(path) as img:
                img_format = img.format
                img_mode = img.mode
                img_size_px = img.size
            self._log(f"Screenshot: {path} | Size: {img_size} bytes | Format: {img_format} | Mode: {img_mode} | Dimensions: {img_size_px}", "INFO")
        except Exception as e:
            self._log(f"Could not get image details: {e}", "WARN")

        prompt = f"""
        Analyze the current screen and describe precisely in a bulleted list.
        You must tell me what window is open, what icons are available, what buttons are shown and / or disabled, what page is open if what you see is a website. What tabs are possibly open and what other UI elements are going to help me take the next step of navigating.
        """ if not prompt else prompt

        self._log(f"Final prompt to LLM: {prompt[:300]}...", "DEBUG")
        msg = [ChatMessage(role=MessageRole.USER, blocks=[ImageBlock(path=path), TextBlock(text=prompt)])]
        self._log(f"Message blocks: {len(msg[0].blocks)} blocks (Image + Text)", "DEBUG")

        response = self.llm.chat(msg)

        # Log raw response details
        self._log(f"LLM Response - Raw object: {response}", "DEBUG")
        self._log(f"LLM Response - Message role: {response.message.role}", "INFO")
        self._log(f"LLM Response - Number of blocks: {len(response.message.blocks)}", "INFO")
        for i, block in enumerate(response.message.blocks):
            block_type = getattr(block, 'block_type', 'unknown')
            block_text = getattr(block, 'text', getattr(block, 'content', 'N/A'))
            self._log(f"LLM Response - Block {i}: type={block_type}, text={str(block_text)[:500]}", "INFO")

        content = "".join([b.text if hasattr(b, 'text') else str(b.content) for b in response.message.blocks])
        if not content and response.message.content:
            content = str(response.message.content)
        self._log(f"LLM Response - Combined content: {content}", "INFO")
        self._clear_screenshots()
        return content
        

if __name__ == "__main__":
    agent = SelfCorrectingVisionAgent()
    if(input("Do you want to analyze the current screen? (y/n): ") == "y"):
        prompt = input("Enter a prompt for the vision agent: ")
        analysis = agent.analyze_current_screen(prompt=prompt)
        print(f"\nANALYSIS: {analysis}")
    else:
        prompt = input("Enter a target to locate on the screen: ")
        res = agent.locate_element(target=prompt)
        print(f"\nRESULT: ({res.x}, {res.y})")