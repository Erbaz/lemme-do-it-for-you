import json
import os
import re
import urllib.request
from dataclasses import dataclass

from llama_index.llms.ollama import Ollama
from llama_index.core.base.llms.types import ChatResponse, TextBlock, ThinkingBlock
from llama_index.core.llms import ChatMessage, ImageBlock, MessageRole, TextBlock
from PIL import Image

from agent.vision_prompts import build_locate_prompt

# Qwen3-VL reports 256K context; LlamaIndex passes that as num_ctx by default,
# which can require ~40 GiB RAM. Screenshots need far less.
DEFAULT_VISION_CONTEXT = 8192
DEFAULT_REQUEST_TIMEOUT = 300.0
# Smaller images = faster vision encoding on CPU/low-VRAM setups.
DEFAULT_MAX_IMAGE_SIZE = 1280


@dataclass
class LocateResult:
    x: int
    y: int
    confidence: str
    window: str
    raw_response: str
    image_width: int
    image_height: int
    screen_width: int
    screen_height: int


class VisionAgent:
    """
    A dedicated vision agent that handles image analysis requests from the Master Agent.
    It uses the Qwen3-VL model via Ollama to analyze screenshots and return text descriptions
    or coordinates.
    """

    def __init__(
        self,
        model_name: str = "qwen3-vl:8b",
        context_window: int = DEFAULT_VISION_CONTEXT,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
        max_image_size: int = DEFAULT_MAX_IMAGE_SIZE,
    ):
        self.model_name = model_name
        self.max_image_size = max_image_size
        self.llm = Ollama(
            model=self.model_name,
            request_timeout=request_timeout,
            context_window=context_window,
            keep_alive="30m",
            # Fix: Pass options here so LlamaIndex registers them properly
            options={"num_predict": 1024, "temperature": 0.0},
        )

    def analyze(self, prompt: str, image_path: str) -> str:
        """General image Q&A (descriptions, reasoning)."""
        if not os.path.exists(image_path):
            return f"Error: Image file not found at {image_path}"

        try:
            prepared_path, width, height, _, _ = self._prepare_image(image_path)
            return self._chat(prepared_path, prompt, think=False)
        except Exception as e:
            return f"Error analyzing image: {str(e)}"

    def locate(self, target: str, image_path: str) -> LocateResult | str:
        """
        Find a UI element and temporarily return the completely unparsed raw string.
        """
        if not os.path.exists(image_path):
            return f"Error: Image file not found at {image_path}"

        try:
            prepared_path, img_w, img_h, screen_w, screen_h = self._prepare_image(
                image_path
            )
            prompt = build_locate_prompt(img_w, img_h, target)

            # 1. Turn off json_mode here
            raw = self._chat(prepared_path, prompt, think=False, json_mode=False)

            # 2. Return the raw response immediately so we can inspect it
            return f"--- RAW MODEL RESPONSE ---\n{raw}\n--------------------------"

        except Exception as e:
            return f"Error locating element: {str(e)}"

    def _chat(
        self,
        image_path: str,
        prompt: str,
        *,
        think: bool = False,
        json_mode: bool = False,
    ) -> str:
        kwargs: dict = {}
        if json_mode:
            kwargs["additional_kwargs"] = {"format": "json"}

        # Anchor text instructions beside the image block to force model compliance
        user_instruction = (
            f"{prompt}\n\n"
            "CRITICAL RULES:\n"
            "- Do not give conversational descriptions, explanations, or thinking tracks.\n"
            "- Directly output only the raw formatted coordinates requested."
        )

        messages = [
            ChatMessage(
                role=MessageRole.SYSTEM,
                content="You are a precise, silent data extraction engine. You never engage in conversation.",
            ),
            ChatMessage(
                role=MessageRole.USER,
                blocks=[
                    ImageBlock(path=image_path),
                    TextBlock(text=user_instruction),
                ],
            ),
        ]

        response = self.llm.chat(messages, **kwargs)
        return self._extract_response_text(response)

    def _prepare_image(self, image_path: str) -> tuple[str, int, int, int, int]:
        """
        Returns (path_for_model, model_image_w, model_image_h, original_w, original_h).
        Downscales large screenshots to speed up vision inference.
        """
        with Image.open(image_path) as img:
            screen_w, screen_h = img.size
            if max(screen_w, screen_h) <= self.max_image_size:
                return image_path, screen_w, screen_h, screen_w, screen_h

            scale = self.max_image_size / max(screen_w, screen_h)
            model_w = int(screen_w * scale)
            model_h = int(screen_h * scale)
            resized = img.resize((model_w, model_h), Image.Resampling.LANCZOS)
            base, _ = os.path.splitext(image_path)
            prepared_path = f"{base}_vision.png"
            resized.save(prepared_path)
            return prepared_path, model_w, model_h, screen_w, screen_h

    @staticmethod
    def _extract_response_text(response: ChatResponse) -> str:
        """Collect text from blocks; Qwen sometimes leaves content empty."""
        parts: list[str] = []
        for block in response.message.blocks:
            if isinstance(block, TextBlock) and block.text:
                parts.append(block.text)
            elif isinstance(block, ThinkingBlock) and block.content:
                parts.append(block.content)
        if parts:
            return "\n".join(parts).strip()

        raw = response.raw
        if isinstance(raw, dict):
            msg = raw.get("message") or {}
            for key in ("content", "thinking"):
                if msg.get(key):
                    return str(msg[key]).strip()
        return ""

    @classmethod
    def _parse_locate_response(
        cls, text: str, image_width: int, image_height: int
    ) -> tuple[int, int, str, str] | None:
        text = (text or "").strip()
        if not text:
            return None

        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if fence:
            text = fence.group(1).strip()

        # Qwen grounding: (x1,y1),(x2,y2) or bbox_2d in prose
        pair = re.search(r"\((\d+)\s*,\s*(\d+)\s*\)\s*,\s*\((\d+)\s*,\s*(\d+)\)", text)
        if pair:
            x1, y1, x2, y2 = map(int, pair.groups())
            return cls._bbox_to_center(x1, y1, x2, y2, image_width, image_height, "")

        bbox_match = re.search(
            r'"bbox_2d"\s*:\s*\[\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*\]',
            text,
        )
        if bbox_match:
            x1, y1, x2, y2 = map(int, bbox_match.groups())
            label = ""
            label_m = re.search(r'"label"\s*:\s*"([^"]*)"', text)
            if label_m:
                label = label_m.group(1)
            return cls._bbox_to_center(x1, y1, x2, y2, image_width, image_height, label)

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            xy = re.search(r'"x"\s*:\s*(-?\d+).*?"y"\s*:\s*(-?\d+)', text, re.DOTALL)
            if xy:
                return (
                    int(xy.group(1)),
                    int(xy.group(2)),
                    "unknown",
                    "",
                )
            return None

        if isinstance(data, list) and data:
            data = data[0]

        if isinstance(data, dict):
            if "bbox_2d" in data and len(data["bbox_2d"]) >= 4:
                x1, y1, x2, y2 = (int(v) for v in data["bbox_2d"][:4])
                return cls._bbox_to_center(
                    x1,
                    y1,
                    x2,
                    y2,
                    image_width,
                    image_height,
                    str(data.get("label", "")),
                )

        if not isinstance(data, dict):
            return None

        if "bbox_2d" in data and len(data["bbox_2d"]) >= 4:
            x1, y1, x2, y2 = (int(v) for v in data["bbox_2d"][:4])
            return cls._bbox_to_center(
                x1,
                y1,
                x2,
                y2,
                image_width,
                image_height,
                str(data.get("label", "")),
            )

        if "x" in data and "y" in data:
            return (
                int(data["x"]),
                int(data["y"]),
                str(data.get("confidence", "unknown")),
                str(data.get("window", data.get("label", ""))),
            )
        return None

    @staticmethod
    def _bbox_to_center(
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        image_width: int,
        image_height: int,
        label: str,
    ) -> tuple[int, int, str, str]:
        # Qwen3-VL may use 0–1000 relative coords on some builds
        if (
            image_width > 0
            and image_height > 0
            and max(x1, y1, x2, y2) <= 1000
            and max(image_width, image_height) > 1000
        ):
            x1 = round(x1 / 1000 * image_width)
            x2 = round(x2 / 1000 * image_width)
            y1 = round(y1 / 1000 * image_height)
            y2 = round(y2 / 1000 * image_height)

        cx = round((x1 + x2) / 2)
        cy = round((y1 + y2) / 2)
        return (cx, cy, "unknown", label)


def print_ollama_runtime_hint() -> str:
    """Report how much of the loaded model sits in VRAM vs system RAM."""
    try:
        with urllib.request.urlopen("http://localhost:11434/api/ps", timeout=3) as resp:
            data = json.loads(resp.read().decode())
    except OSError:
        return ""

    lines: list[str] = []
    for model in data.get("models", []):
        name = model.get("name", "?")
        total = model.get("size") or 0
        vram = model.get("size_vram") or 0
        ctx = model.get("context_length", "?")
        if total <= 0:
            continue
        vram_pct = 100.0 * vram / total
        ram_pct = 100.0 - vram_pct
        if vram_pct >= 99:
            device = "GPU (full)"
        elif vram_pct <= 1:
            device = "CPU/RAM (no VRAM — check drivers or GPU)"
        else:
            device = f"hybrid ~{vram_pct:.0f}% GPU / ~{ram_pct:.0f}% CPU+RAM"
        lines.append(
            f"Ollama runtime [{name}]: {device}, "
            f"VRAM {vram / (1024**3):.1f} GB / {total / (1024**3):.1f} GB, "
            f"context={ctx}"
        )
    return "\n".join(lines)
