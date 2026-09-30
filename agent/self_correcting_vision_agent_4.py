import json
import os
import re
import shutil
import time
import random
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Tuple, Dict

import pyautogui
import pytweening
from PIL import Image, ImageDraw, ImageFont

import agent.model
import agent.logger_setup as log_setup
from llama_index.core import Settings
from llama_index.core.base.llms.types import TextBlock
from llama_index.core.llms import ChatMessage, ImageBlock, MessageRole
from llama_index.llms.ollama import Ollama

pyautogui.FAILSAFE = False


@dataclass
class LocateResult:
    """Final result of element localization."""
    target: str
    x: int
    y: int
    confidence: str
    iterations: int
    screen_width: int
    screen_height: int


class SelfCorrectingVisionAgentV4:
    """V4: Self-Correcting Vision Agent with Crop-and-Zoom.
    8x8 grid, crop-and-zoom, dual-image verification."""
    GRID_SIZE = 8
    CELL_SIZE = 1000 / GRID_SIZE

    def __init__(self, model_name="qwen3-vl:4b-instruct", context_window=8192,
                 request_timeout=300.0, max_image_size=1280, grid_divisions=8,
                 verbose=True, cleanup_screenshots=True):
        self.model_name = model_name
        self.max_image_size = max_image_size
        self.grid_divisions = grid_divisions
        self.verbose = verbose
        self.cleanup_screenshots = cleanup_screenshots
        self.llm = Settings.llm if Settings.llm else Ollama(
            model=self.model_name, request_timeout=request_timeout,
            context_window=context_window,
            options={"num_predict": 1024, "temperature": 0.0})
        self.history = []
        self._thoughts = []
        self.current_grid_vector = None
        self.current_crop_region = None
        self.current_crop_image_path = None
        self.last_good_crop_region = None
        self.last_good_grid_vector = None
        self.zoom_level = 0
        self.curr_nx = None
        self.curr_ny = None
        self._image_count = 0
        self.logger = log_setup.get_logger()
        self.incrementer = log_setup.get_token_incrementer()
        self.incrementer.context_window = context_window
        log_setup.update_context_window(context_window)
        self.logger.info(f"Session started | Model: {model_name} | V4 Crop-and-Zoom")

    def _log(self, msg, level="INFO"):
        if self.verbose:
            print(f"[{time.strftime('%H:%M:%S')}] [{level}] {msg}")

    # === Thought Tracking ===
    def clear_thought_process(self):
        self._thoughts = []
    def get_thought_process(self):
        return self._thoughts
    def _add_thought(self, thought):
        self._thoughts.append(thought)

    # === Coordinate Math ===
    def _norm_to_native(self, nx, ny):
        sw, sh = pyautogui.size()
        return int((nx / 1000) * sw), int((ny / 1000) * sh)
    def _norm_to_model_img(self, nx, ny, mw, mh):
        return int((nx / 1000) * mw), int((ny / 1000) * mh)

    # === Grid Vector Methods ===
    def _get_grid_vector(self, nx, ny):
        row = min(7, max(0, int(ny * 8 / 1000)))
        col = min(7, max(0, int(nx * 8 / 1000)))
        return f"{row} x {col}"
    def _grid_vector_to_bounds(self, grid_vector):
        try:
            parts = grid_vector.split("x")
            row, col = int(parts[0]), int(parts[1])
        except:
            row, col = 0, 0
        return (col * self.CELL_SIZE, (col+1)*self.CELL_SIZE, row * self.CELL_SIZE, (row+1)*self.CELL_SIZE)
    def _sub_grid_to_full_norm(self, grid_vector, crop_region):
        try:
            row, col = int(grid_vector.split("x")[0]), int(grid_vector.split("x")[1])
        except:
            row, col = 0, 0
        x_min, x_max, y_min, y_max = crop_region
        cw, ch = (x_max-x_min)/self.GRID_SIZE, (y_max-y_min)/self.GRID_SIZE
        return int(x_min+(col+0.5)*cw), int(y_min+(row+0.5)*ch)

    # === Image Processing ===
    def _get_font(self):
        try:
            return ImageFont.truetype("arial.ttf", 12)
        except:
            return ImageFont.load_default()

    def capture_processed_screenshot(self, output_path, curr_norm=None,
                                       draw_grid=True, draw_crosshair=True,
                                       history_points=None, grid_overlay=True):
        sw, sh = pyautogui.size()
        scale = self.max_image_size / max(sw, sh)
        mw, mh = int(sw*scale), int(sh*scale)
        img = pyautogui.screenshot().resize((mw,mh), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(img)
        font = self._get_font()
        if draw_grid and grid_overlay:
            gc = [int(1000*i/self.grid_divisions) for i in range(1,self.grid_divisions)]
            gc_color = (255,255,0,200)
            for gx in gc:
                draw.line([(int((gx/1000)*mw),0),(int((gx/1000)*mw),mh)], fill=gc_color, width=1)
            for gy in gc:
                draw.line([(0,int((gy/1000)*mh)),(mw,int((gy/1000)*mh))], fill=gc_color, width=1)
            if grid_overlay:
                for gx in gc:
                    for gy in gc:
                        px,py = self._norm_to_model_img(gx,gy,mw,mh)
                        label = f"({gx},{gy})"
                        draw.ellipse([px-3,py-3,px+3,py+3], fill="yellow", outline="black")
                        bbox = draw.textbbox((px+5,py+3), label, font=font)
                        draw.rectangle([bbox[0]-2,bbox[1]-1,bbox[2]+2,bbox[3]+1], fill=(0,0,0,180), outline="yellow")
                        draw.text((px+5,py+3), label, fill="yellow", font=font)
        hist_points = history_points if history_points is not None else self.history
        hc = ["cyan","#FF00FF","#00FF00","#FFA500","#00FFFF","#FF69B4"]
        for i,pos in enumerate(hist_points[:6]):
            hx,hy = self._norm_to_model_img(pos[0],pos[1],mw,mh)
            draw.ellipse([hx-8,hy-8,hx+8,hy+8], fill=hc[i%6], outline="black", width=2)
        if draw_crosshair and curr_norm:
            cx,cy = self._norm_to_model_img(curr_norm[0],curr_norm[1],mw,mh)
            draw.line([(cx-25,cy),(cx-6,cy)], fill="red", width=2)
            draw.line([(cx+6,cy),(cx+25,cy)], fill="red", width=2)
            draw.line([(cx,cy-25),(cx,cy-6)], fill="red", width=2)
            draw.line([(cx,cy+6),(cx,cy+25)], fill="red", width=2)
            draw.ellipse([cx-2,cy-2,cx+2,cy+2], fill="red")
            draw.ellipse([cx-14,cy-14,cx+14,cy+14], outline="red", width=2)
        img.save(output_path)
        return output_path, mw, mh

    def _extract_crop(self, img, crop_region, mw, mh):
        x_min,x_max,y_min,y_max = crop_region
        px_min = max(0,min(int((x_min/1000)*mw), img.width))
        px_max = max(0,min(int((x_max/1000)*mw), img.width))
        py_min = max(0,min(int((y_min/1000)*mh), img.height))
        py_max = max(0,min(int((y_max/1000)*mh), img.height))
        if px_max<=px_min: px_max=px_min+1
        if py_max<=py_min: py_max=py_min+1
        return img.crop((px_min,py_min,px_max,py_max)).resize((mw,mh), Image.Resampling.LANCZOS)

    def capture_cropped_screenshot(self, output_path, crop_region, draw_grid=True,
                                     draw_crosshair=True, crosshair_norm=None, grid_overlay=True):
        sw,sh = pyautogui.size()
        scale = self.max_image_size / max(sw,sh)
        mw,mh = int(sw*scale), int(sh*scale)
        img = pyautogui.screenshot().resize((mw,mh), Image.Resampling.LANCZOS)
        img = self._extract_crop(img, crop_region, mw, mh)
        draw = ImageDraw.Draw(img)
        font = self._get_font()
        if draw_grid and grid_overlay:
            gc = [int(1000*i/self.grid_divisions) for i in range(1,self.grid_divisions)]
            gc_color = (255,255,0,200)
            for gx in gc:
                draw.line([(int((gx/1000)*mw),0),(int((gx/1000)*mw),mh)], fill=gc_color, width=1)
            for gy in gc:
                draw.line([(0,int((gy/1000)*mh)),(mw,int((gy/1000)*mh))], fill=gc_color, width=1)
            if grid_overlay:
                for gx in gc:
                    for gy in gc:
                        px,py = self._norm_to_model_img(gx,gy,mw,mh)
                        label = f"({gx},{gy})"
                        draw.ellipse([px-3,py-3,px+3,py+3], fill="yellow", outline="black")
                        bbox = draw.textbbox((px+5,py+3), label, font=font)
                        draw.rectangle([bbox[0]-2,bbox[1]-1,bbox[2]+2,bbox[3]+1], fill=(0,0,0,180), outline="yellow")
                        draw.text((px+5,py+3), label, fill="yellow", font=font)
        if draw_crosshair and crosshair_norm:
            cx,cy = self._norm_to_model_img(crosshair_norm[0],crosshair_norm[1],mw,mh)
            draw.line([(cx-25,cy),(cx-6,cy)], fill="red", width=2)
            draw.line([(cx+6,cy),(cx+25,cy)], fill="red", width=2)
            draw.line([(cx,cy-25),(cx,cy-6)], fill="red", width=2)
            draw.line([(cx,cy+6),(cx,cy+25)], fill="red", width=2)
            draw.ellipse([cx-2,cy-2,cx+2,cy+2], fill="red")
            draw.ellipse([cx-14,cy-14,cx+14,cy+14], outline="red", width=2)
        img.save(output_path)
        return output_path, mw, mh

    def _capture_screenshot_with_scaling(self, output_path):
        sw,sh = pyautogui.size()
        scale = self.max_image_size / max(sw,sh)
        mw,mh = int(sw*scale), int(sh*scale)
        img = pyautogui.screenshot().resize((mw,mh), Image.Resampling.LANCZOS)
        img.save(output_path)
        return output_path, mw, mh

    # === Prompt Methods ===
    def _get_initial_locate_prompt(self, target):
        return f'''A yellow 8x8 grid overlay divides this screenshot into 64 cells.
Locate "{target}" and tell me which grid cell contains it.
Return ONLY valid JSON: {{"grid_vector": "row x column", "x": integer, "y": integer}}
Row and column are 0-7.'''

    def _get_crop_locate_prompt(self, target, grid_vector):
        return f'''This is a zoomed-in crop with an 8x8 grid overlay.
The target is "{target}". The parent grid position was {grid_vector}.
Move the crosshair to the sub-cell containing the target.
Return ONLY valid JSON: {{"x": integer, "y": integer, "grid_vector": "row x column"}}
Row and column should be 0-7.'''

    def _get_verify_in_grid_prompt(self, target):
        return f'''This is a CLEAN crop with an 8x8 grid overlay and NO crosshairs or markers.
Is the target element "{target}" visible anywhere within this cropped grid region?
Return ONLY valid JSON: {{"target_in_grid": true_or_false, "reason": "describe what you see"}}'''

    def _get_verify_crosshair_prompt(self, target):
        return f'''A RED crosshair marks the center of this cropped screenshot.
The target element is "{target}".
Describe ONLY what is at the red crosshair position.
Return ONLY valid JSON:
{{"target_at_crosshair": true_or_false, "description": "what you see at the red crosshair"}}'''

    def _get_reestimate_prompt(self, target, grid_vector):
        return f'''This is a zoomed-in crop with 8x8 grid and a RED crosshair at center.
The target is "{target}". The current grid position is {grid_vector}.
The crosshair is NOT on the target. Move to a DIFFERENT grid cell.
Return ONLY valid JSON: {{"x": integer, "y": integer, "grid_vector": "row x column"}}
Row and column should be 0-7.'''

    def _get_reset_crop_prompt(self, target, grid_vector):
        return f'''This is a zoomed-in crop with an 8x8 grid overlay.
The target element is "{target}". The previous position was {grid_vector}.
The target was confirmed in this crop, but the crosshair was not on it.
Move the crosshair to the sub-cell containing the target.
Return ONLY valid JSON: {{"x": integer, "y": integer, "grid_vector": "row x column"}}
Row and column should be 0-7.'''

    # === LLM Chat ===
    def _chat(self, image_path, prompt):
        msg = [ChatMessage(role=MessageRole.USER, blocks=[ImageBlock(path=image_path), TextBlock(text=prompt)])]
        try:
            img_size = os.path.getsize(image_path)
            with Image.open(image_path) as img:
                self._log(f"Image: {image_path} | {img_size} bytes | {img.format}", "DEBUG")
        except Exception as e:
            self._log(f"Could not get image details: {e}", "WARN")
        self._add_thought(f"Prompt: {prompt[:200]}...")
        log_setup.reset_token_counts()
        response = self.llm.chat(msg)
        tokens = log_setup.get_token_snapshot()
        summary = self.incrementer.record_call(tokens["prompt_tokens"], tokens["completion_tokens"])
        self.logger.info(f"LLM Call #{summary['call_number']} | Prompt: {tokens['prompt_tokens']} | Cum: {summary['cumulative_total']} | Usage: {summary['percent_used']}%")
        content = "".join([b.text if hasattr(b,'text') else str(b.content) for b in response.message.blocks])
        if not content and response.message.content:
            content = str(response.message.content)
        self._add_thought(f"Response: {content[:200]}...")
        match = re.search(r"\{[\s\S]*\}", content)
        if not match:
            raise ValueError(f"No JSON found in LLM response: {content}")
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON from LLM: {match.group(0)}")

    # === Mouse Movement ===
    def _humanly_move_cursor_to(self, target_x, target_y):
        start_x, start_y = pyautogui.position()
        duration = random.uniform(0.4, 0.9)
        mid_x = (start_x+target_x)/2 + random.randint(-60,60)
        mid_y = (start_y+target_y)/2 + random.randint(-60,60)
        steps = 18
        for i in range(steps+1):
            t = i/steps
            t = pytweening.easeInOutQuad(t)
            cx = (1-t)**2*start_x + 2*(1-t)*t*mid_x + t**2*target_x
            cy = (1-t)**2*start_y + 2*(1-t)*t*mid_y + t**2*target_y
            pyautogui.moveTo(cx+random.uniform(-0.5,0.5), cy+random.uniform(-0.5,0.5))
            time.sleep(duration/steps)

    def _clear_screenshots(self):
        if not self.cleanup_screenshots:
            return
        archive_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".logs", "screenshots", datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
        os.makedirs(archive_dir, exist_ok=True)
        for file in os.listdir("."):
            if file.startswith("iter_") and file.endswith(".png"):
                src, dst = os.path.join(".",file), os.path.join(archive_dir,file)
                try:
                    shutil.move(src, dst)
                    self.logger.info(f"Archived screenshot: {file}")
                except Exception as e:
                    self.logger.warning(f"Failed to archive {file}: {e}")

    # === Main Locating Workflow ===
    def locate_element(self, target, max_iterations=5):
        sw, sh = pyautogui.size()
        self.history = []
        self._thoughts = []
        self._image_count = 0
        self._log(f"V4 locate_element '{target}' | Max: {max_iterations}", "STEP")
        self._add_thought(f"Starting localization: {target}")
        try:
            # PHASE 1: Full Screen 8x8 Grid
            self._log("PHASE 1: Full screen grid selection", "STEP")
            fp = f"iter_{self._image_count + 1}.png"
            self.capture_processed_screenshot(fp, draw_grid=True, draw_crosshair=False, grid_overlay=True)
            data = self._chat(fp, self._get_initial_locate_prompt(target))
            gv = data.get("grid_vector", "0 x 0")
            curr_nx = int(data.get("x", 500))
            curr_ny = int(data.get("y", 500))
            self._add_thought(f"Grid cell: {gv}")
            crop_region = self._grid_vector_to_bounds(gv)
            self.current_grid_vector = gv
            self.current_crop_region = crop_region
            self.last_good_crop_region = crop_region
            self.last_good_grid_vector = gv

            # PHASE 2: Cropped Region
            self._log("PHASE 2: Cropped region zoom", "STEP")
            cp = f"iter_{self._image_count + 1}_crop.png"
            self.capture_cropped_screenshot(cp, crop_region, draw_grid=True, draw_crosshair=True,
                                                 crosshair_norm=(curr_nx,curr_ny), grid_overlay=True)
            data = self._chat(cp, self._get_crop_locate_prompt(target, gv))
            sgv = data.get("grid_vector", "0 x 0")
            curr_nx, curr_ny = self._sub_grid_to_full_norm(sgv, crop_region)
            self.last_good_grid_vector = sgv
            self.curr_nx, self.curr_ny = curr_nx, curr_ny

            # PHASE 3: Verification Loop
            for iteration in range(1, max_iterations + 1):
                px, py = self._norm_to_native(curr_nx, curr_ny)
                self._humanly_move_cursor_to(px, py)
                ch_path = f"iter_{self._image_count + 1}_crosshair.png"
                self.capture_cropped_screenshot(ch_path, crop_region, draw_grid=True, draw_crosshair=True,
                                                 crosshair_norm=(curr_nx,curr_ny), grid_overlay=True)
                cl_path = f"iter_{self._image_count + 1}_clean.png"
                self.capture_cropped_screenshot(cl_path, crop_region, draw_grid=True, draw_crosshair=False, grid_overlay=True)

                # Verify: Is target in the grid?
                ig_data = self._chat(cl_path, self._get_verify_in_grid_prompt(target))
                target_in_grid = ig_data.get("target_in_grid", False)
                if not target_in_grid:
                    if self.last_good_crop_region:
                        crop_region = self.last_good_crop_region
                        rp = f"iter_{self._image_count + 1}_reset.png"
                        self.capture_cropped_screenshot(rp, crop_region, draw_grid=True, draw_crosshair=False, grid_overlay=True)
                        rd = self._chat(rp, self._get_reset_crop_prompt(target, self.last_good_grid_vector))
                        curr_nx, curr_ny = self._sub_grid_to_full_norm(rd.get("grid_vector","0 x 0"), crop_region)
                    self.history.insert(0, (curr_nx, curr_ny))
                    if len(self.history) > 6: self.history.pop()
                    continue

                # Verify: Is target at crosshair?
                tc_data = self._chat(ch_path, self._get_verify_crosshair_prompt(target))
                if tc_data.get("target_at_crosshair", False):
                    result = LocateResult(target, px, py, "high", iteration, sw, sh)
                    return result

                # Re-estimate
                re_path = f"iter_{self._image_count + 1}_reestimate.png"
                self.capture_cropped_screenshot(re_path, crop_region, draw_grid=True, draw_crosshair=True,
                                                 crosshair_norm=(curr_nx,curr_ny), grid_overlay=True)
                re_data = self._chat(re_path, self._get_reestimate_prompt(target, self.last_good_grid_vector))
                curr_nx = max(0, min(1000, int(re_data.get("x", curr_nx))))
                curr_ny = max(0, min(1000, int(re_data.get("y", curr_ny))))
                self.history.insert(0, (curr_nx, curr_ny))
                if len(self.history) > 6: self.history.pop()

            px, py = self._norm_to_native(curr_nx, curr_ny)
            return LocateResult(target, px, py, "low", max_iterations, sw, sh)
        finally:
            self._clear_screenshots()

    # === Screen Analysis ===
    def analyze_current_screen(self, prompt=None, screenshot_path=None):
        self._log(f"prompt from master agent: {prompt}")
        path = screenshot_path or "current_screen.png"
        if not screenshot_path:
            self._capture_screenshot_with_scaling(path)
        prompt_text = prompt or "Analyze the current screen and describe precisely in a bulleted list."
        msg = [ChatMessage(role=MessageRole.USER, blocks=[ImageBlock(path=path), TextBlock(text=prompt_text)])]
        log_setup.reset_token_counts()
        response = self.llm.chat(msg)
        tokens = log_setup.get_token_snapshot()
        summary = self.incrementer.record_call(tokens["prompt_tokens"], tokens["completion_tokens"])
        self.logger.info(f"LLM Call #{summary['call_number']} | Prompt: {tokens['prompt_tokens']} | Cum: {summary['cumulative_total']}")
        content = "".join([b.text if hasattr(b,'text') else str(b.content) for b in response.message.blocks])
        if not content and response.message.content:
            content = str(response.message.content)
        return content


if __name__ == "__main__":
    import time
    agent = SelfCorrectingVisionAgentV4(cleanup_screenshots=False)
    if input("Analyze screen? (y/n): ") == "y":
        prompt = input("Enter prompt: ")
        analysis = agent.analyze_current_screen(prompt=prompt)
        print(f"\nANALYSIS: {analysis}")
    else:
        prompt = input("Enter target: ")
        time.sleep(5)
        res = agent.locate_element(target=prompt)
        print(f"\nRESULT: ({res.x}, {res.y}) [Confidence: {res.confidence}, Iterations: {res.iterations}]")