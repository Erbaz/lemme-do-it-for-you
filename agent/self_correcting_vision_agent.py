import json
import os
import re
import time
from dataclasses import dataclass
from typing import Optional, List, Tuple

import pyautogui
from llama_index.llms.ollama import Ollama
from llama_index.core import Settings
from llama_index.core.base.llms.types import ChatResponse, TextBlock, ThinkingBlock
from llama_index.core.llms import ChatMessage, ImageBlock, MessageRole
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
        return f"""The RED crosshair is at normalized coordinates ({nx}, {ny}). 
It is NOT on the center of the "{target}".

Task: Nudge the RED crosshair. How many units (on a 0-1000 scale) must we move it in X and Y to reach the center of the "{target}"? Use previous coordinates marked in image to understand how much to nudge in proportion.
Return ONLY JSON: {{"offset_x": <int>, "offset_y": <int>}}"""

    # ==================== Main Workflow ====================

    def _chat(self, image_path: str, prompt: str) -> dict:
        msg = [ChatMessage(role=MessageRole.USER, blocks=[ImageBlock(path=image_path), TextBlock(text=prompt)])]
        response = self.llm.chat(msg, additional_kwargs={"format": "json", "num_predict": 1024})
        print(f"response: {response}")
        content = "".join([b.text if hasattr(b, 'text') else b.content for b in response.message.blocks])
        match = re.search(r"\{[\s\S]*\}", content)
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

    def analyze_current_screen(self, prompt:str | None) -> str:
        self._log(f"prompt from master agent: {prompt}")
        path = "current_screen.png"
        self._capture_screenshot_with_scaling(path)
        prompt = f"""
        Analyze the current screen and describe precisely in a bulleted list.
        You must tell me what window is open, what icons are available, what buttons are shown and / or disabled, what page is open if what you see is a website. What tabs are possibly open and what other UI elements are going to help me take the next step of navigating.
        """ if not prompt else prompt
        msg = [ChatMessage(role=MessageRole.USER, blocks=[ImageBlock(path=path), TextBlock(text=prompt)])]
        response = self.llm.chat(msg, additional_kwargs={"num_predict": 1024})
        self._log(f"response: {response}")
        content = "".join([b.text if hasattr(b, 'text') else b.content for b in response.message.blocks])
        self._clear_screenshots()
        return content
        

if __name__ == "__main__":
    Settings.llm = Ollama(model="qwen3-vl:4b-instruct", request_timeout=120.0, context_window=8192)
    agent = SelfCorrectingVisionAgent()
    if(input("Do you want to analyze the current screen? (y/n): ") == "y"):
        analysis = agent.analyze_current_screen()
        print(f"\nANALYSIS: {analysis}")
    else:
        res = agent.locate_element(target="the docker app")
        print(f"\nRESULT: ({res.x}, {res.y})")