import json
import os
import re
import shutil
import time
import random
from datetime import datetime
from dataclasses import dataclass
from typing import Optional, List, Tuple

import pyautogui
import pytweening
from PIL import Image, ImageDraw, ImageFont

import agent.model  # loads model config from .env and sets Settings.llm
import agent.logger_setup as log_setup  # session logging, token counting
from llama_index.core import Settings
from llama_index.core.base.llms.types import TextBlock
from llama_index.core.llms import ChatMessage, ImageBlock, MessageRole
from llama_index.llms.ollama import Ollama

# DISABLE FAILSAFE so we can reach corner buttons
pyautogui.FAILSAFE = False


@dataclass
class LocateResult:
    """Final result of element localization."""
    target: str
    x: int  # Native Screen X
    y: int  # Native Screen Y
    confidence: str
    iterations: int
    screen_width: int
    screen_height: int


class SelfCorrectingVisionAgentV3:
    def __init__(
        self,
        model_name: str = "qwen3-vl:4b-instruct",
        context_window: int = 8192,
        request_timeout: float = 300.0,
        max_image_size: int = 1280,
        grid_divisions: int = 9,  # 8 interior lines divide into 9 bands
        verbose: bool = True,
        cleanup_screenshots: bool = True,
    ):
        self.model_name = model_name
        self.max_image_size = max_image_size
        self.grid_divisions = grid_divisions
        self.verbose = verbose
        self.cleanup_screenshots = cleanup_screenshots
        self.llm = Settings.llm if Settings.llm else Ollama(
            model=self.model_name,
            request_timeout=request_timeout,
            context_window=context_window,
            options={"num_predict": 1024, "temperature": 0.0},
        )
        # Store failed points in NORMALIZED (0-1000) space
        self.history: List[Tuple[int, int]] = []

        # ---- Logging & Token Tracking ----
        self.logger = log_setup.get_logger()
        self.incrementer = log_setup.get_token_incrementer()
        self.incrementer.context_window = context_window
        log_setup.update_context_window(context_window)

        self.logger.info(
            f"Session started | Model: {model_name} | "
            f"Context Window: {context_window} | "
            f"Log file: {log_setup.LOG_FILE_PATH.name}"
        )
        self.logger.info(
            f"TokenIncrementer initialized | context_window={context_window}"
        )

    def _log(self, msg: str, level: str = "INFO"):
        if self.verbose:
            print(f"[{time.strftime('%H:%M:%S')}] [{level}] {msg}")

    # ==================== Coordinate Math ====================

    def _norm_to_native(self, nx: int, ny: int) -> Tuple[int, int]:
        sw, sh = pyautogui.size()
        return int((nx / 1000) * sw), int((ny / 1000) * sh)

    def _norm_to_model_img(self, nx: int, ny: int, mw: int, mh: int) -> Tuple[int, int]:
        return int((nx / 1000) * mw), int((ny / 1000) * mh)

    def _capture_screenshot_with_scaling(self, output_path: str):
        sw, sh = pyautogui.size()
        scale = self.max_image_size / max(sw, sh)
        mw, mh = int(sw * scale), int(sh * scale)

        img = pyautogui.screenshot()
        img = img.resize((mw, mh), Image.Resampling.LANCZOS)
        img.save(output_path)

    # ==================== Image Processing with 4x4 Grid Overlay ====================

    def _get_font(self):
        try:
            return ImageFont.truetype("arial.ttf", 12)
        except Exception:
            return ImageFont.load_default()

    def capture_processed_screenshot(
        self,
        output_path: str,
        curr_norm: Optional[Tuple[int, int]] = None,
        draw_grid: bool = True,
    ) -> Tuple[str, int, int]:
        sw, sh = pyautogui.size()
        scale = self.max_image_size / max(sw, sh)
        mw, mh = int(sw * scale), int(sh * scale)

        img = pyautogui.screenshot()
        img = img.resize((mw, mh), Image.Resampling.LANCZOS)
        draw = ImageDraw.Draw(img)
        font = self._get_font()

        # 1. Draw 8x8 Grid Lines with coordinate labels
        if draw_grid:
            grid_coords = [int(1000 * i / self.grid_divisions) for i in range(1, self.grid_divisions)]
            grid_color = (255, 255, 0, 200)  # more opaque yellow
            for gx in grid_coords:
                px = int((gx / 1000) * mw)
                draw.line([(px, 0), (px, mh)], fill=grid_color, width=1)
            for gy in grid_coords:
                py = int((gy / 1000) * mh)
                draw.line([(0, py), (mw, py)], fill=grid_color, width=1)
            # Draw coordinate labels at all intersection points
            for gx in grid_coords:
                for gy in grid_coords:
                    px, py = self._norm_to_model_img(gx, gy, mw, mh)
                    label = f"({gx},{gy})"
                    r = 3
                    draw.ellipse([px - r, py - r, px + r, py + r], fill="yellow", outline="black")
                    bbox = draw.textbbox((px + 5, py + 3), label, font=font)
                    draw.rectangle([bbox[0] - 2, bbox[1] - 1, bbox[2] + 2, bbox[3] + 1], fill=(0, 0, 0, 180), outline="yellow")
                    draw.text((px + 5, py + 3), label, fill="yellow", font=font)

        # 2. Draw History Points (colored dots only, no labels)
        history_colors = ["cyan", "#FF00FF", "#00FF00", "#FFA500", "#00FFFF", "#FF69B4"]
        for i, pos in enumerate(self.history[:6]):
            hx, hy = self._norm_to_model_img(pos[0], pos[1], mw, mh)
            color = history_colors[i % len(history_colors)]
            r = 8
            draw.ellipse([hx - r, hy - r, hx + r, hy + r], fill=color, outline="black", width=2)

        # 3. Draw Current (RED Local Target Ring - NO screen-wide lines)
        if curr_norm:
            cx, cy = self._norm_to_model_img(curr_norm[0], curr_norm[1], mw, mh)
            tick_len = 25
            gap = 6
            # Crosshair ticks that do NOT cross the whole screen
            draw.line([(cx - tick_len, cy), (cx - gap, cy)], fill="red", width=2)
            draw.line([(cx + gap, cy), (cx + tick_len, cy)], fill="red", width=2)
            draw.line([(cx, cy - tick_len), (cx, cy - gap)], fill="red", width=2)
            draw.line([(cx, cy + gap), (cx, cy + tick_len)], fill="red", width=2)

            # Center dot and target ring
            r_dot = 2
            draw.ellipse([cx - r_dot, cy - r_dot, cx + r_dot, cy + r_dot], fill="red")
            r_ring = 14
            draw.ellipse([cx - r_ring, cy - r_ring, cx + r_ring, cy + r_ring], outline="red", width=2)

        img.save(output_path)
        return output_path, mw, mh

    # ==================== Prompt Methods (Direct Re-estimation) ====================

    def _get_grid_vector(self, nx: int, ny: int) -> str:
        """Return grid position as 'row x column' for 9x9 grid."""
        row = int(ny * 9 / 1000)
        col = int(nx * 9 / 1000)
        return f"{row} x {col}"

    # ==================== Prompt Methods (Direct Re-estimation) ====================

    def _get_locate_prompt(self, target: str) -> str:
        return f"""A RED crosshair marks the current guess position on this screenshot.
A yellow grid overlay shows position markers with coordinate labels like (222,444) at each intersection.
Locate "{target}" in the screenshot and give its grid vector AND coordinates.
Return ONLY valid JSON: {{"x": integer, "y": integer, "grid_vector": "row x column"}}"""

    def _get_verify_prompt(self, target: str) -> str:
        return f"""Look at the RED crosshair at the center of this image.
Describe ONLY what you see at the red crosshair position — do NOT give coordinates.
Do NOT tell me where the target is. Just describe what is at the crosshair location.
Answer ONLY with a JSON object:
{{"description": "what you see at the red crosshair"}}"""

    def _get_reestimate_prompt(self, target: str, nx: int, ny: int) -> str:
        gv = self._get_grid_vector(nx, ny)
        return f"""A RED crosshair is at ({nx}, {ny}), which is grid position {gv}.
The target is "{target}". Move the crosshair to a DIFFERENT grid position and give new coordinates.
The grid has labeled intersections like (222,444). Use them for spatial reference.
Return ONLY valid JSON: {{"x": integer, "y": integer, "grid_vector": "row x column"}}"""


    def _create_cumulative_map(self, full_screenshot_path: str) -> str:
        """Create a dedicated spatial map showing ALL crosshair positions with connection lines."""
        img = Image.open(full_screenshot_path)
        draw = ImageDraw.Draw(img)
        font = self._get_font()
        history_colors = ["cyan", "#FF00FF", "#00FF00", "#FFA500", "#00FFFF", "#FF69B4"]

        # Draw lines connecting all previous crosshair positions to show trajectory
        all_positions = list(self.history)  # most recent first
        if len(all_positions) >= 2:
            for i in range(len(all_positions) - 1):
                p1 = all_positions[i]
                p2 = all_positions[i + 1]
                x1, y1 = self._norm_to_model_img(p1[0], p1[1], img.width, img.height)
                x2, y2 = self._norm_to_model_img(p2[0], p2[1], img.width, img.height)
                color = history_colors[i % len(history_colors)]
                draw.line([(x1, y1), (x2, y2)], fill=color, width=2)

        # Redraw all labels on top for clarity
        for i, pos in enumerate(all_positions[:6]):
            hx, hy = self._norm_to_model_img(pos[0], pos[1], img.width, img.height)
            color = history_colors[i % len(history_colors)]
            h_label = f"T{i+1}:({pos[0]},{pos[1]})"
            h_bbox = draw.textbbox((hx + 10, hy - 8), h_label, font=font)
            draw.rectangle([h_bbox[0] - 2, h_bbox[1] - 1, h_bbox[2] + 2, h_bbox[3] + 1], fill="black", outline=color)
            draw.text((hx + 10, hy - 8), h_label, fill=color, font=font)

        map_path = full_screenshot_path.replace(".png", "_map.png")
        img.save(map_path)
        return map_path

    # ==================== LLM Chat ====================

    def _chat(self, image_path: str, prompt: str) -> dict:
        msg = [ChatMessage(role=MessageRole.USER, blocks=[ImageBlock(path=image_path), TextBlock(text=prompt)])]

        try:
            img_size = os.path.getsize(image_path)
            with Image.open(image_path) as img:
                img_format = img.format
                img_mode = img.mode
            self._log(f"Image: {image_path} | Size: {img_size} bytes | Format: {img_format} | Mode: {img_mode}", "DEBUG")
        except Exception as e:
            self._log(f"Could not get image details: {e}", "WARN")

        self._log(f"Sending prompt to LLM: {prompt}", "DEBUG")

        # ---- Token tracking ----
        log_setup.reset_token_counts()
        response = self.llm.chat(msg)
        tokens = log_setup.get_token_snapshot()
        summary = self.incrementer.record_call(tokens["prompt_tokens"], tokens["completion_tokens"])

        self.logger.info(
            f"LLM Call #{summary['call_number']} | "
            f"Prompt tokens: {tokens['prompt_tokens']} | "
            f"Completion tokens: {tokens['completion_tokens']} | "
            f"Cumulative total: {summary['cumulative_total']} | "
            f"Context: {summary['context_window']} | "
            f"Remaining: {summary['remaining_tokens']} | "
            f"Usage: {summary['percent_used']}%"
        )

        content = "".join([b.text if hasattr(b, 'text') else str(b.content) for b in response.message.blocks])
        if not content and response.message.content:
            content = str(response.message.content)
        self._log(f"LLM Response - Combined content: {content}", "DEBUG")

        match = re.search(r"\{[\s\S]*\}", content)
        if not match:
            self._log(f"ERROR: No JSON found in response! Content: {content}", "ERROR")
            raise ValueError(f"No JSON found in LLM response: {content}")
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            self._log(f"ERROR: Invalid JSON from LLM: {match.group(0)}", "ERROR")
            raise ValueError(f"Invalid JSON from LLM: {match.group(0)}")

    # ==================== Mouse Movement ====================

    def _humanly_move_cursor_to(self, target_x: int, target_y: int):
        start_x, start_y = pyautogui.position()
        duration = random.uniform(0.4, 0.9)
        mid_x = (start_x + target_x) / 2 + random.randint(-60, 60)
        mid_y = (start_y + target_y) / 2 + random.randint(-60, 60)

        steps = 18
        for i in range(steps + 1):
            t = i / steps
            t = pytweening.easeInOutQuad(t)
            curr_x = (1 - t) ** 2 * start_x + 2 * (1 - t) * t * mid_x + t ** 2 * target_x
            curr_y = (1 - t) ** 2 * start_y + 2 * (1 - t) * t * mid_y + t ** 2 * target_y
            jitter_x = random.uniform(-0.5, 0.5)
            jitter_y = random.uniform(-0.5, 0.5)
            pyautogui.moveTo(curr_x + jitter_x, curr_y + jitter_y)
            time.sleep(duration / steps)

    def _clear_screenshots(self):
        if not self.cleanup_screenshots:
            return
        archive_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            ".logs", "screenshots", datetime.now().strftime("%Y-%m-%d_%H-%M-%S"),
        )
        os.makedirs(archive_dir, exist_ok=True)
        for file in os.listdir("."):
            if file.startswith("iter_") and file.endswith(".png"):
                src = os.path.join(".", file)
                dst = os.path.join(archive_dir, file)
                try:
                    shutil.move(src, dst)
                    self.logger.info(f"Archived screenshot: {file} -> {os.path.basename(archive_dir)}/")
                except Exception as e:
                    self.logger.warning(f"Failed to archive {file}: {e}")

    # ==================== Main Locating Workflow ====================

    def locate_element(self, target: str, max_iterations: int = 5) -> LocateResult:
        sw, sh = pyautogui.size()
        self.history = []

        # --- Step 0: Absolute Guess with Grid Overlay ---
        path = "iter_0.png"
        self.capture_processed_screenshot(path, draw_grid=True)
        data = self._chat(path, self._get_locate_prompt(target))
        curr_nx, curr_ny = int(data["x"]), int(data["y"])

        try:
            for i in range(1, max_iterations + 1):
                # Move Native Mouse
                px, py = self._norm_to_native(curr_nx, curr_ny)
                self._log(f"Iteration {i}: Checking Native ({px}, {py}) | Norm ({curr_nx}, {curr_ny})", "STEP")
                self._humanly_move_cursor_to(px, py)

                # Capture with Grid + Crosshair + History
                path = f"iter_{i}.png"
                path, mw, mh = self.capture_processed_screenshot(path, curr_norm=(curr_nx, curr_ny), draw_grid=True)

                # 1. Verify: describe what's at the crosshair (for logging only)
                v_data = self._chat(path, self._get_verify_prompt(target))
                v_desc = v_data.get("description", "")
                self._log(f"Iteration {i} Verification: desc='{v_desc[:80]}...'", "DEBUG")

                # 2. Direct Re-estimation using CUMULATIVE CROSSHAIR MAP
                self.history.insert(0, (curr_nx, curr_ny))
                if len(self.history) > 6:
                    self.history.pop()

                # Create cumulative map showing ALL crosshair positions with trajectory
                map_path = self._create_cumulative_map(path)
                re_data = self._chat(map_path, self._get_reestimate_prompt(target, curr_nx, curr_ny))
                if os.path.exists(map_path):
                    try:
                        os.remove(map_path)
                    except Exception:
                        pass
                new_nx = max(0, min(1000, int(re_data["x"])))
                new_ny = max(0, min(1000, int(re_data["y"])))
                new_gv = self._get_grid_vector(new_nx, new_ny)
                old_gv = self._get_grid_vector(curr_nx, curr_ny)

                self._log(f"Iteration {i}: Re-estimated ({curr_nx},{curr_ny}) -> ({new_nx},{new_ny}) | grid {old_gv} -> {new_gv}", "STEP")
                curr_nx, curr_ny = new_nx, new_ny

                # Convergence check: same grid_vector for 2+ iterations
                if hasattr(self, '_last_gv') and self._last_gv == new_gv:
                    self._log(f"SUCCESS: Converged at grid {new_gv} | ({curr_nx}, {curr_ny})", "DONE")
                    px, py = self._norm_to_native(curr_nx, curr_ny)
                    result = LocateResult(target, px, py, "high", i, sw, sh)
                    self.logger.info(
                        f"SUCCESS | Target '{target}' converged at iteration {i} | "
                        f"Result: ({result.x}, {result.y}) | "
                        f"Total tokens used: {self.incrementer._cumulative_total} | "
                        f"Total LLM calls: {self.incrementer._call_count}"
                    )
                    return result
                self._last_gv = new_gv

            px, py = self._norm_to_native(curr_nx, curr_ny)
            result = LocateResult(target, px, py, "low", max_iterations, sw, sh)
            self.logger.info(
                f"Session complete | Result: ({result.x}, {result.y}) | "
                f"Confidence: {result.confidence} | Iterations: {result.iterations} | "
                f"Total tokens used: {self.incrementer._cumulative_total} | "
                f"Total LLM calls: {self.incrementer._call_count}"
            )
            return result

        finally:
            self._clear_screenshots()

    # ==================== Screen Analysis ====================

    def analyze_current_screen(self, prompt: str | None = None, screenshot_path: str | None = None) -> str:
        self._log(f"prompt from master agent: {prompt}")
        path = screenshot_path or "current_screen.png"
        if not screenshot_path:
            self._capture_screenshot_with_scaling(path)

        prompt_text = f"""
        Analyze the current screen and describe precisely in a bulleted list.
        You must tell me what window is open, what icons are available, what buttons are shown and / or disabled, what page is open if what you see is a website. What tabs are possibly open and what other UI elements are going to help me take the next step of navigating.
        """ if not prompt else prompt

        msg = [ChatMessage(role=MessageRole.USER, blocks=[ImageBlock(path=path), TextBlock(text=prompt_text)])]

        # ---- Token tracking ----
        log_setup.reset_token_counts()
        response = self.llm.chat(msg)
        tokens = log_setup.get_token_snapshot()
        summary = self.incrementer.record_call(tokens["prompt_tokens"], tokens["completion_tokens"])

        self.logger.info(
            f"LLM Call #{summary['call_number']} | "
            f"Prompt tokens: {tokens['prompt_tokens']} | "
            f"Completion tokens: {tokens['completion_tokens']} | "
            f"Cumulative total: {summary['cumulative_total']} | "
            f"Context: {summary['context_window']} | "
            f"Remaining: {summary['remaining_tokens']} | "
            f"Usage: {summary['percent_used']}%"
        )

        content = "".join([b.text if hasattr(b, 'text') else str(b.content) for b in response.message.blocks])
        if not content and response.message.content:
            content = str(response.message.content)
        self._log(f"LLM Response - Combined content: {content}", "INFO")

        if self.cleanup_screenshots and not screenshot_path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                pass

        return content


if __name__ == "__main__":
    # Set cleanup_screenshots=False during interactive testing so you can review iter_*.png files
    import time
    agent = SelfCorrectingVisionAgentV3(cleanup_screenshots=False)
    if input("Do you want to analyze the current screen? (y/n): ") == "y":
        prompt = input("Enter a prompt for the vision agent: ")
        analysis = agent.analyze_current_screen(prompt=prompt)
        print(f"\nANALYSIS: {analysis}")
    else:
        prompt = input("Enter a target to locate on the screen: ")
        time.sleep(5)
        res = agent.locate_element(target=prompt)
        print(f"\nRESULT: ({res.x}, {res.y}) [Confidence: {res.confidence}, Iterations: {res.iterations}]")
