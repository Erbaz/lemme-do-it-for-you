
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
        max_image_size: int = 1920,
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
        self.history: List[Tuple[int, int]] = []
        self.target_grid_box: Optional[str] = None

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
        scale = self.max_image_size / max(sw, sh)
        mw, mh = int(sw * scale), int(sh * scale)
        
        img = pyautogui.screenshot()
        img = img.resize((mw, mh), Image.Resampling.LANCZOS)
        img.save(output_path)

    # ==================== Masking Helper ====================

    def _get_grid_mask(self, img: Image.Image, box_id: str) -> Image.Image:
        w, h = img.size
        mask = Image.new("RGB", (w, h), "black")
        rows, cols = 3, 2
        box_idx = int(box_id) - 1
        row = box_idx // cols
        col = box_idx % cols
        box_w, box_h = w // cols, h // rows
        x1, y1 = col * box_w, row * box_h
        x2, y2 = x1 + box_w, y1 + box_h
        roi = img.crop((x1, y1, x2, y2))
        mask.paste(roi, (x1, y1))
        return mask

    # ==================== Image Processing ====================

    def capture_processed_screenshot(self, output_path: str, curr_norm: Optional[Tuple[int, int]] = None) -> Tuple[str, int, int]:
        sw, sh = pyautogui.size()
        scale = self.max_image_size / max(sw, sh)
        mw, mh = int(sw * scale), int(sh * scale)
        
        img = pyautogui.screenshot()
        img = img.resize((mw, mh), Image.Resampling.LANCZOS)
        
        if self.target_grid_box:
            img = self._get_grid_mask(img, self.target_grid_box)
            
        draw = ImageDraw.Draw(img)

        colors = ["cyan", "#FF00FF"] 
        for i, pos in enumerate(self.history[:2]):
            hx, hy = self._norm_to_model_img(pos[0], pos[1], mw, mh)
            r = 10
            draw.ellipse([hx-r, hy-r, hx+r, hy+r], fill=colors[i])

        if curr_norm:
            cx, cy = self._norm_to_model_img(curr_norm[0], curr_norm[1], mw, mh)
            draw.line([(0, cy), (mw, cy)], fill="red", width=2)
            draw.line([(cx, 0), (cx, mh)], fill="red", width=2)
            r = 20
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline="red", width=2)

        img.save(output_path)
        return output_path, mw, mh

    # ==================== Prompt Methods ====================

    def _get_locate_prompt(self, target: str) -> str:
        return f"""You are a computer vision engine. 
Task: Find the exact center coordinates of "{target}".
Use a normalized coordinate system from 0 to 1000, where (0,0) is top-left and (1000,1000) is bottom-right.
NOTE: Part of this image is masked in black. IGNORE the black area and focus ONLY on the visible content to locate the target.
Return ONLY JSON: {{"x": <0-1000>, "y": <0-1000>}}"""

    def _get_verify_prompt(self, target: str, nx: int, ny: int) -> str:
        return f"""The RED crosshair is centered exactly at ({nx}, {ny}).
Is the center of the RED crosshair touching or overlapping the "{target}"?
NOTE: Part of the screen is masked in black. IGNORE the black area and focus ONLY on the visible content to determine if the crosshair is touching the target.
Return ONLY JSON: {{"confirmed": true or false}}"""

    def _get_offset_prompt(self, target: str, nx: int, ny: int) -> str:
        return f"""The RED crosshair is at ({nx}, {ny}). It is NOT on the "{target}".
How many units (0-1000 scale) must we move in X and Y to reach the center?
NOTE: Part of this image is masked in black. IGNORE the black area and focus ONLY on the visible content to locate the target.
Return ONLY JSON: {{"offset_x": <int>, "offset_y": <int>}}"""

    # ==================== Workflow Methods ====================

    def _chat(self, image_path: str, prompt: str) -> dict:
        msg = [ChatMessage(role=MessageRole.USER, blocks=[ImageBlock(path=image_path), TextBlock(text=prompt)])]
        try:
            response = self.llm.chat(msg, additional_kwargs={"reasoning": {"effort": "none"}})
        except Exception:
            response = self.llm.chat(msg)
        content = "".join([b.text if hasattr(b, 'text') else b.content for b in response.message.blocks])
        match = re.search(r"\{[\s\S]*\}", content)
        return json.loads(match.group(0))

    def analyze_current_screen(self, prompt:str | None = None) -> str:
        self._log(f"prompt from master agent: {prompt}")
        path = "current_screen.png"
        self._capture_screenshot_with_scaling(path)
        prompt = f"""
        Analyze the current screen and describe precisely in a bulleted list.
        You must tell me what window is open, what icons are available, what buttons are shown and / or disabled, what page is open if what you see is a website. What tabs are possibly open and what other UI elements are going to help me take the next step of navigating.
        """ if not prompt else prompt
        msg = [ChatMessage(role=MessageRole.USER, blocks=[ImageBlock(path=path), TextBlock(text=prompt)])]
        try:
            response = self.llm.chat(msg, additional_kwargs={"reasoning": {"effort": "none"}})
        except Exception:
            response = self.llm.chat(msg)
        content = "".join([b.text if hasattr(b, 'text') else b.content for b in response.message.blocks])
        # self._clear_screenshots()
        return content

    def analyze_screen_with_masking(self, prompt: str) -> dict:
        path = "analysis.png"
        sw, sh = pyautogui.size()
        scale = self.max_image_size / max(sw, sh)
        mw, mh = int(sw * scale), int(sh * scale)
        img = pyautogui.screenshot()
        img = img.resize((mw, mh), Image.Resampling.LANCZOS)
        
        draw = ImageDraw.Draw(img)
        rows, cols = 3, 2
        box_w, box_h = mw // cols, mh // rows
        for r in range(1, rows): draw.line([(0, r*box_h), (mw, r*box_h)], fill="red", width=2)
        for c in range(1, cols): draw.line([(c*box_w, 0), (c*box_w, mh)], fill="red", width=2)
        img.save(path)
        
        # full_prompt = f"{prompt}. Return ONLY JSON with fields 'analysis' (str) and 'target_grid_box' (str, '1'-'6'). The grid lines are outlined with red lines on the image. The top left corner is box 1, the one to its right is 2, the second row starts with box 3, and so on."
        full_prompt = f"""
            QUERY: {prompt}

            CRITICAL: You must identify which grid box contains the target.
            The screen is divided into 6 segments (3 rows, 2 columns):
            - Box 1: Top-Left    | Box 2: Top-Right
            - Box 3: Middle-Left | Box 4: Middle-Right
            - Box 5: Bottom-Left | Box 6: Bottom-Right
            Return ONLY JSON with fields 'analysis' (str) and 'target_grid_box' (str '1' through '6').
        """
        
        data = self._chat(path, full_prompt)
        self.target_grid_box = data.get("target_grid_box")
        return data

    def _humanly_move_cursor_to(self, target_x, target_y):
        start_x, start_y = pyautogui.position()
        duration = random.uniform(0.5, 1.2)
        mid_x = (start_x + target_x) / 2 + random.randint(-100, 100)
        mid_y = (start_y + target_y) / 2 + random.randint(-100, 100)
        steps = 20
        for i in range(steps + 1):
            t = pytweening.easeInOutQuad(i / steps)
            curr_x = (1-t)**2 * start_x + 2*(1-t)*t * mid_x + t**2 * target_x
            curr_y = (1-t)**2 * start_y + 2*(1-t)*t * mid_y + t**2 * target_y
            pyautogui.moveTo(curr_x + random.uniform(-0.5, 0.5), curr_y + random.uniform(-0.5, 0.5))
            time.sleep(duration / steps)
    
    def _clear_screenshots(self):
        # self._clear_screenshots is commented out as requested
        pass

    def locate_element(self, target: str, max_iterations: int = 5):
        sw, sh = pyautogui.size()
        self.history = []
        path = "iter_0.png"
        self.capture_processed_screenshot(path)
        data = self._chat(path, self._get_locate_prompt(target))
        curr_nx, curr_ny = int(data["x"]), int(data["y"])
        try:
            for i in range(1, max_iterations + 1):
                px, py = self._norm_to_native(curr_nx, curr_ny)
                self._humanly_move_cursor_to(px, py)
                path = f"iter_{i}.png"
                self.capture_processed_screenshot(path, curr_norm=(curr_nx, curr_ny))
                v_data = self._chat(path, self._get_verify_prompt(target, curr_nx, curr_ny))
                if v_data.get("confirmed") is True:
                    return LocateResult(target, px, py, "high", i, sw, sh)
                self.history.insert(0, (curr_nx, curr_ny))
                if len(self.history) > 3: self.history.pop()
                o_data = self._chat(path, self._get_offset_prompt(target, curr_nx, curr_ny))
                curr_nx = max(0, min(1000, curr_nx + int(o_data.get("offset_x", 0))))
                curr_ny = max(0, min(1000, curr_ny + int(o_data.get("offset_y", 0))))
            px, py = self._norm_to_native(curr_nx, curr_ny)
            return LocateResult(target, px, py, "low", max_iterations, sw, sh)
        finally:
            self._clear_screenshots()





if __name__ == "__main__":
    import agent.model  # ensures Settings.llm is configured from .env
    agent = SelfCorrectingVisionAgent()
    analysis_prompt = input("Analysis prompt: ")
    if(analysis_prompt):
        analysis = agent.analyze_screen_with_masking(prompt=analysis_prompt)
        print(f"\nANALYSIS: {analysis}")
    
    target = input("Target: ")
    if(target):
        res = agent.locate_element(target=target)
        print(f"\nRESULT: ({res.x}, {res.y})")