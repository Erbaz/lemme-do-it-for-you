import json
import logging
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
    OVERLAP_PERCENTAGE = 0.10  # 10% overlap between grid cells for border element confidence

    def __init__(self, model_name="qwen3-vl:4b-instruct", context_window=8192,
                 request_timeout=300.0, max_image_size=1280, grid_divisions=8,
                 overlap_percentage=0.10, verbose=True, cleanup_screenshots=True):
        self.model_name = model_name
        self.max_image_size = max_image_size
        self.grid_divisions = grid_divisions
        self.overlap_percentage = overlap_percentage
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
        actual_model = self.llm.model if hasattr(self.llm, "model") else model_name
        self.logger.info(f"Session started | Model: {actual_model} | V4 Crop-and-Zoom | Overlap: {overlap_percentage*100}%")

    def _log(self, msg, level="INFO"):
        if self.verbose:
            print(f"[{time.strftime('%H:%M:%S')}] [{level}] {msg}")
        self.logger.log(getattr(logging, level.upper(), logging.INFO), msg)

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

    def _parse_grid_vector(self, grid_vector):
        """Parse a grid_vector string in various formats into (row, col).
        Handles '7x5', '7 x 5', '7 5', '7x5', etc.
        Always returns clamped values in range [0, GRID_SIZE-1]."""
        gv = grid_vector.strip()
        row, col = 0, 0
        try:
            if 'x' in gv.lower():
                parts = gv.lower().split('x')
                row = int(parts[0].strip())
                col = int(parts[1].strip())
            else:
                # Space-separated format like "7 5"
                parts = gv.replace(',', ' ').split()
                if len(parts) >= 2:
                    row = int(parts[0])
                    col = int(parts[1])
        except (ValueError, IndexError):
            pass
        # Clamp to valid grid range
        row = max(0, min(self.GRID_SIZE - 1, row))
        col = max(0, min(self.GRID_SIZE - 1, col))
        return row, col

    def _grid_vector_to_bounds(self, grid_vector, overlap_pct=None):
        row, col = self._parse_grid_vector(grid_vector)
        
        # Use provided overlap_pct or fall back to instance default
        pct = overlap_pct if overlap_pct is not None else self.overlap_percentage
        overlap = self.CELL_SIZE * pct
        
        # Calculate bounds with overlap, clamped to 0-1000 range
        x_min = max(0, col * self.CELL_SIZE - overlap)
        x_max = min(1000, (col + 1) * self.CELL_SIZE + overlap)
        y_min = max(0, row * self.CELL_SIZE - overlap)
        y_max = min(1000, (row + 1) * self.CELL_SIZE + overlap)
        
        return (x_min, x_max, y_min, y_max)
    def _sub_grid_to_full_norm(self, grid_vector, crop_region):
        row, col = self._parse_grid_vector(grid_vector)
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
            # Convert full-screen normalized coords to crop-relative pixel coords
            x_min, x_max, y_min, y_max = crop_region
            crop_w = x_max - x_min
            crop_h = y_max - y_min
            if crop_w > 0 and crop_h > 0:
                cx = int(((crosshair_norm[0] - x_min) / crop_w) * mw)
                cy = int(((crosshair_norm[1] - y_min) / crop_h) * mh)
                cx = max(0, min(mw - 1, cx))
                cy = max(0, min(mh - 1, cy))
            else:
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
Rows are numbered 0-7 from TOP, columns 0-7 from LEFT (ZERO-INDEXED).
Locate "{target}" and tell me which grid cell contains it.
Return ONLY valid JSON: {{"grid_vector": "row x column"}}
Row and column are ZERO-INDEXED integers 0-7.'''

    def _get_crop_locate_prompt(self, target, grid_vector):
        return f'''This is a zoomed-in crop with an 8x8 grid overlay.
Rows are numbered 0-7 from TOP, columns 0-7 from LEFT (ZERO-INDEXED).
The target is "{target}". The parent grid position was {grid_vector}.
Move the crosshair to the sub-cell containing the target.
Return ONLY valid JSON: {{"grid_vector": "row x column"}}
Row and column are ZERO-INDEXED integers 0-7.'''

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
Rows are numbered 0-7 from TOP, columns 0-7 from LEFT (ZERO-INDEXED).
The target is "{target}". The current grid position is {grid_vector}.
The crosshair is NOT on the target. Move to a DIFFERENT grid cell.
Return ONLY valid JSON: {{"x": <0-1000>, "y": <0-1000>, "grid_vector": "row x column"}}
Row and column are ZERO-INDEXED integers 0-7. X and Y are normalized coordinates (0-1000).'''

    def _get_reset_crop_prompt(self, target, grid_vector):
        return f'''This is a zoomed-in crop with an 8x8 grid overlay.
Rows are numbered 0-7 from TOP, columns 0-7 from LEFT (ZERO-INDEXED).
The target element is "{target}". The previous crop grid position was {grid_vector}.
The target was NOT visible in this crop region.
Return ONLY valid JSON: {{"grid_vector": "row x column"}}
Suggest a DIFFERENT grid cell (row x column) that might contain the target.
Row and column are ZERO-INDEXED integers 0-7.'''

    # === LLM Chat ===
    def _chat(self, image_path, prompt):
        msg = [ChatMessage(role=MessageRole.USER, blocks=[ImageBlock(path=image_path), TextBlock(text=prompt)])]
        try:
            img_size = os.path.getsize(image_path)
            with Image.open(image_path) as img:
                self._log(f"Image: {image_path} | {img_size} bytes | {img.format} | {img.mode} | {img.size}", "DEBUG")
        except Exception as e:
            self._log(f"Could not get image details: {e}", "WARN")
        self._add_thought(f"Prompt: {prompt[:200]}...")
        self.logger.info(f"=== LLM REQUEST ===")
        self.logger.info(f"Image: {image_path}")
        self.logger.info(f"Prompt (full):\n{prompt}")
        log_setup.reset_token_counts()
        response = self.llm.chat(msg)
        tokens = log_setup.get_token_snapshot()
        summary = self.incrementer.record_call(tokens["prompt_tokens"], tokens["completion_tokens"])
        self.logger.info(f"LLM Call #{summary['call_number']} | Prompt tokens: {tokens['prompt_tokens']} | Completion tokens: {tokens['completion_tokens']} | Cumulative: {summary['cumulative_total']} | Usage: {summary['percent_used']}%")
        content = "".join([b.text if hasattr(b,'text') else str(b.content) for b in response.message.blocks])
        if not content and response.message.content:
            content = str(response.message.content)
        self._add_thought(f"Response: {content[:200]}...")
        self.logger.info(f"=== LLM RESPONSE (raw) ===")
        for i, block in enumerate(response.message.blocks):
            block_type = getattr(block, 'block_type', 'unknown')
            block_text = getattr(block, 'text', getattr(block, 'content', 'N/A'))
            self.logger.info(f"Block {i}: type={block_type}, text={str(block_text)[:10000]}")
        self.logger.info(f"=== LLM RESPONSE (combined content) ===")
        self.logger.info(content)
        match = re.search(r"\{[\s\S]*\}", content)
        if not match:
            self.logger.error(f"No JSON found in LLM response! Content: {content}")
            raise ValueError(f"No JSON found in LLM response: {content}")
        try:
            parsed = json.loads(match.group(0))
            self.logger.info(f"=== PARSED JSON OUTPUT ===")
            self.logger.info(json.dumps(parsed, indent=2))
        except json.JSONDecodeError:
            self.logger.error(f"Invalid JSON from LLM: {match.group(0)}")
            raise ValueError(f"Invalid JSON from LLM: {match.group(0)}")
        return parsed

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
        log_setup.reset_token_counts()
        self._log(f"V4 locate_element '{target}' | Max: {max_iterations}", "STEP")
        self._add_thought(f"Starting localization: {target}")
        self.logger.info(f"=== LOCATE ELEMENT START: target='{target}', max_iterations={max_iterations}, screen={sw}x{sh}, overlap={self.overlap_percentage*100}% ===")
        try:
            # PHASE 1: Full Screen 8x8 Grid
            self._log("PHASE 1: Full screen grid selection", "STEP")
            fp = f"iter_{self._image_count + 1}.png"
            self.capture_processed_screenshot(fp, draw_grid=True, draw_crosshair=False, grid_overlay=True)
            data = self._chat(fp, self._get_initial_locate_prompt(target))
            gv = data.get("grid_vector", "0 x 0")
            crop_region = self._grid_vector_to_bounds(gv)
            # Compute normalized coordinates from grid_vector center (not LLM's x/y)
            # Compute center of grid cell on full screen (Phase 1: full-screen grid)
            p1_row, p1_col = self._parse_grid_vector(gv)
            curr_nx = int((p1_col + 0.5) * self.CELL_SIZE)
            curr_ny = int((p1_row + 0.5) * self.CELL_SIZE)
            self._add_thought(f"Grid cell: {gv}")
            self._log(f"Initial grid vector: {gv}, normalized coords: ({curr_nx}, {curr_ny})", "STEP")
            self.logger.info(f"PHASE 1 COMPLETE: grid_vector={gv}, norm_coords=({curr_nx}, {curr_ny})")
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
            self._log(f"Sub-grid vector: {sgv}, full normalized coords: ({curr_nx}, {curr_ny})", "STEP")
            self.logger.info(f"PHASE 2 COMPLETE: sub_grid_vector={sgv}, full_norm_coords=({curr_nx}, {curr_ny}), crop_region={crop_region}")

            # PHASE 3: Verification Loop
            for iteration in range(1, max_iterations + 1):
                px, py = self._norm_to_native(curr_nx, curr_ny)
                self._humanly_move_cursor_to(px, py)
                self.logger.info(f"=== ITERATION {iteration}/{max_iterations} ===")
                self.logger.info(f"Cursor moved to native ({px}, {py}) | normalized ({curr_nx}, {curr_ny})")
                ch_path = f"iter_{self._image_count + 1}_crosshair.png"
                self.capture_cropped_screenshot(ch_path, crop_region, draw_grid=True, draw_crosshair=True,
                                                 crosshair_norm=(curr_nx,curr_ny), grid_overlay=True)
                cl_path = f"iter_{self._image_count + 1}_clean.png"
                self.capture_cropped_screenshot(cl_path, crop_region, draw_grid=True, draw_crosshair=False, grid_overlay=True)

                # Verify: Is target in the grid?
                ig_data = self._chat(cl_path, self._get_verify_in_grid_prompt(target))
                target_in_grid = ig_data.get("target_in_grid", False)
                self.logger.info(f"VERIFY IN-GRID: target_in_grid={target_in_grid}, reason={ig_data.get('reason', 'N/A')[:500]}")
                if not target_in_grid:
                    self.logger.info(f"Target NOT in current grid region. Initiating depth reduction...")
                    # DEPTH REDUCTION: Go back to full screen to find a new grid cell
                    fp = f"iter_{self._image_count + 1}_depth_reduce.png"
                    self.capture_processed_screenshot(fp, draw_grid=True, draw_crosshair=False, grid_overlay=True)
                    dr_data = self._chat(fp, self._get_initial_locate_prompt(target))
                    gv = dr_data.get("grid_vector", "0 x 0")
                    prev_nx, prev_ny = curr_nx, curr_ny
                    new_crop_region = self._grid_vector_to_bounds(gv)
                    # Compute coordinates from grid_vector center, not LLM's inconsistent x/y
                    # Compute center of grid cell on full screen (depth reduction: full-screen grid)
                    dr_row, dr_col = self._parse_grid_vector(gv)
                    curr_nx = int((dr_col + 0.5) * self.CELL_SIZE)
                    curr_ny = int((dr_row + 0.5) * self.CELL_SIZE)
                    self.logger.info(f"DEPTH REDUCTION: grid_vector={gv}, moved from ({prev_nx}, {prev_ny}) to ({curr_nx}, {curr_ny}), new crop_region={new_crop_region}")
                    # Re-run Phase 2 with new grid cell
                    cp = f"iter_{self._image_count + 1}_depth_recrop.png"
                    self.capture_cropped_screenshot(cp, new_crop_region, draw_grid=True, draw_crosshair=True,
                                                         crosshair_norm=(curr_nx,curr_ny), grid_overlay=True)
                    data = self._chat(cp, self._get_crop_locate_prompt(target, gv))
                    sgv = data.get("grid_vector", "0 x 0")
                    curr_nx, curr_ny = self._sub_grid_to_full_norm(sgv, new_crop_region)
                    self.last_good_grid_vector = sgv
                    crop_region = new_crop_region
                    self.current_crop_region = crop_region
                    self.current_grid_vector = gv
                    self.logger.info(f"DEPTH REDUCTION Phase 2 complete: sub_grid={sgv}, coords=({curr_nx}, {curr_ny})")
                    self.history.insert(0, (curr_nx, curr_ny))
                    if len(self.history) > 6: self.history.pop()
                    continue

                # Verify: Is target at crosshair?
                tc_data = self._chat(ch_path, self._get_verify_crosshair_prompt(target))
                self.logger.info(f"VERIFY CROSSHAIR: target_at_crosshair={tc_data.get('target_at_crosshair', False)}, description={tc_data.get('description', 'N/A')[:500]}")
                if tc_data.get("target_at_crosshair", False):
                    result = LocateResult(target, px, py, "high", iteration, sw, sh)
                    self.logger.info(f"=== SUCCESS: Target confirmed at crosshair ({px}, {py}) | iterations={iteration} ===")
                    self._log(f"SUCCESS: Confirmed at iteration {iteration} | ({px}, {py})", "DONE")
                    return result

                # Re-estimate
                re_path = f"iter_{self._image_count + 1}_reestimate.png"
                self.capture_cropped_screenshot(re_path, crop_region, draw_grid=True, draw_crosshair=True,
                                                 crosshair_norm=(curr_nx,curr_ny), grid_overlay=True)
                re_data = self._chat(re_path, self._get_reestimate_prompt(target, self.last_good_grid_vector))
                prev_nx, prev_ny = curr_nx, curr_ny
                # Use grid_vector from LLM for precise sub-cell position (preferred)
                re_gv = re_data.get("grid_vector", self.last_good_grid_vector)
                if re_gv and re_gv != self.last_good_grid_vector:
                    curr_nx, curr_ny = self._sub_grid_to_full_norm(re_gv, crop_region)
                else:
                    # grid_vector unchanged or missing - use LLM's x/y
                    # Convert crop-relative normalized coords (0-1000 within crop) 
                    # to full-screen normalized coords
                    llm_x = re_data.get("x", curr_nx)
                    llm_y = re_data.get("y", curr_ny)
                    if llm_x is not None and llm_y is not None:
                        x_min, x_max, y_min, y_max = crop_region
                        crop_w = x_max - x_min
                        crop_h = y_max - y_min
                        if crop_w > 0 and crop_h > 0:
                            curr_nx = max(0, min(1000, int(x_min + (int(llm_x) / 1000) * crop_w)))
                            curr_ny = max(0, min(1000, int(y_min + (int(llm_y) / 1000) * crop_h)))
                self.logger.info(f"RE-ESTIMATE: moved from ({prev_nx}, {prev_ny}) to ({curr_nx}, {curr_ny})")
                self.history.insert(0, (curr_nx, curr_ny))
                if len(self.history) > 6: self.history.pop()
                self._image_count += 1
                # Oscillation detection: if we've been at the same position 3+ times, force a jump
                same_count = sum(1 for (hx, hy) in self.history if hx == curr_nx and hy == curr_ny)
                if same_count >= 3:
                    self.logger.info(f"OSCILLATION DETECTED: stuck at ({curr_nx}, {curr_ny}) for {same_count} iterations. Forcing position change.")
                    # Force a jump to a neighboring grid cell
                    neighbor_dx = random.randint(-100, 100)
                    neighbor_dy = random.randint(-100, 100)
                    curr_nx = max(0, min(1000, curr_nx + neighbor_dx))
                    curr_ny = max(0, min(1000, curr_ny + neighbor_dy))
                    self.logger.info(f"Forced jump to ({curr_nx}, {curr_ny})")

            px, py = self._norm_to_native(curr_nx, curr_ny)
            self.logger.info(f"=== MAX ITERATIONS REACHED: returning ({px}, {py}) with low confidence ===")
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


    # === Grid Cell Locator ===
    def locate_gridcell(self, target, screenshot_path=None, grid_divisions=8):
        """Standalone method: capture a screenshot with an 8x8 grid overlay,
        ask the LLM which grid cell contains the target, and log the full
        model reasoning alongside the extracted grid_vector.

        Args:
            target:           Text description of the UI element to find.
            screenshot_path:  Optional pre-captured screenshot path. If None,
                              a fresh full-screen capture with grid overlay
                              is taken.
            grid_divisions:   Number of divisions per axis (default 8 → 64 cells).

        Returns:
            dict with keys:
                grid_vector       – str  e.g. "6x4"
                norm_x, norm_y    – int  normalized 0-1000 coords (grid center)
                px, py            – int  pixel coords on the physical screen
                reasoning         – str  the full LLM response text (may include thinking)
                screenshot        – str  path of the screenshot that was sent
        """
        path = screenshot_path or f"gridcell_query_{self._image_count + 1}.png"
        if not screenshot_path:
            self.capture_processed_screenshot(
                path, draw_grid=True, draw_crosshair=False, grid_overlay=True
            )
        self._image_count += 1

        prompt_text = (
            f"A yellow 8x8 grid overlay divides this screenshot into 64 cells "
            f"(rows 0-7 from top, columns 0-7 from left, ZERO-INDEXED). "
            f"Example: the top-left cell is row 0, column 0; "
            f"the bottom-right cell is row 7, column 7. "
            f"Locate \"{target}\" and tell me which grid cell contains it. "
            f"First explain your step-by-step visual reasoning, then "
            f"return ONLY a JSON snippet: {{\"grid_vector\": \"row x column\"}} "
            f"where row and column are ZERO-INDEXED integers 0-7."
        )

        msg = [ChatMessage(
            role=MessageRole.USER,
            blocks=[ImageBlock(path=path), TextBlock(text=prompt_text)]
        )]

                                        
        # Reset token counts for this call
        log_setup.reset_token_counts()
        response = self.llm.chat(msg)


        # Capture full raw response text (this is where reasoning lives)
        full_response = "".join(
            b.text if hasattr(b, "text") else str(b.content)
            for b in response.message.blocks
        )
        if not full_response and response.message.content:
            full_response = str(response.message.content)

        # Log the FULL model output — reasoning + JSON
        self.logger.info(f"GRIDCELL QUERY: target='{target}'")
        self.logger.info(f"LLM RAW RESPONSE:\n{full_response}")
        self._log(f"LLM full response for '{target}':\n{full_response}", "INFO")

        # Record tokens
        tokens = log_setup.get_token_snapshot()
        summary = self.incrementer.record_call(
            tokens["prompt_tokens"], tokens["completion_tokens"]
        )
        self.logger.info(
            f"LLM Call #{summary['call_number']} | "
            f"Prompt: {tokens['prompt_tokens']} | "
            f"Cum: {summary['cumulative_total']}"
        )

        # Parse grid_vector from JSON (may be embedded after reasoning text)
        grid_vector = "0 x 0"
        # Look for JSON object in the response
        json_match = re.search(r'\{[^{}]*\"grid_vector\"\s*:\s*\"([^\"]+)\"[^{}]*\}', full_response, re.DOTALL)
        if json_match:
            grid_vector = json_match.group(1).strip()
        else:
            # Fallback: look for "row x col" or "row col" pattern
            gv_match = re.search(r'(\d+)\s*[xX\s]\s*(\d+)', full_response)
            if gv_match:
                grid_vector = f"{gv_match.group(1)} x {gv_match.group(2)}"

        # Normalize grid_vector: convert "7 5" to "7x5" if no 'x' present
        if 'x' not in grid_vector.lower():
            # Handle space-separated format like "7 5"
            parts = grid_vector.split()
            if len(parts) == 2:
                grid_vector = f"{parts[0]} x {parts[1]}"

        # Normalize spacing in grid_vector for parsing
        gv_clean = grid_vector.replace(" ", "").lower()

        # Compute normalized coords from grid vector center
        row, col = 0, 0
        try:
            parts = gv_clean.split("x")
            row = int(parts[0])
            col = int(parts[1])
        except (ValueError, IndexError):
            pass

        # Clamp to valid grid range (0-7 for 8x8)
        row = max(0, min(self.GRID_SIZE - 1, row))
        col = max(0, min(self.GRID_SIZE - 1, col))

        cell = 1000 // self.GRID_SIZE  # 125 for 8x8
        curr_nx = int((col + 0.5) * cell)
        curr_ny = int((row + 0.5) * cell)

        px, py = self._norm_to_native(curr_nx, curr_ny)

        self.logger.info(
            f"GRIDCELL RESULT: target='{target}' | "
            f"grid_vector={grid_vector} | "
            f"norm_coords=({curr_nx}, {curr_ny}) | "
            f"pixel_coords=({px}, {py})"
        )

        return {
            "grid_vector": grid_vector,
            "norm_x": curr_nx,
            "norm_y": curr_ny,
            "px": px,
            "py": py,
            "reasoning": full_response,
            "screenshot": path,
        }


if __name__ == "__main__":
    import time
    agent = SelfCorrectingVisionAgentV4(cleanup_screenshots=False)
    choice = input("Analyze screen (a), locate element (l), or gridcell query (g)? ").strip().lower()
    if choice == "a":
        prompt = input("Enter prompt: ")
        analysis = agent.analyze_current_screen(prompt=prompt)
        print(f"\nANALYSIS: {analysis}")
    elif choice == "g":
        target = input("Enter target: ")
        time.sleep(2)
        result = agent.locate_gridcell(target=target)
        print(f"\nGRIDCELL RESULT:")
        print(f"  Target:       {target}")
        print(f"  Grid vector:  {result['grid_vector']}  (row x col)")
        print(f"  Norm coords:  ({result['norm_x']}, {result['norm_y']})")
        print(f"  Pixel coords: ({result['px']}, {result['py']})")
        print(f"  LLM reasoning:\n{result['reasoning']}")
    else:
        prompt = input("Enter target: ")
        time.sleep(5)
        res = agent.locate_element(target=prompt)
        print(f"\nRESULT: ({res.x}, {res.y}) [Confidence: {res.confidence}, Iterations: {res.iterations}]")