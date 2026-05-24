"""Prompt templates for VisionAgent tasks."""

LOCATE_ELEMENT_PROMPT = """The image is exactly {width}x{height} pixels (origin top-left).

Task: Find the exact bounding box for: "{target}"

Your response must follow this format exactly. Do not include markdown code blocks, do not include any introductory phrases, and do not explain your thinking. Just output these 4 lines with the numbers:

x1: <number>
y1: <number>
x2: <number>
y2: <number>"""


def build_locate_prompt(width: int, height: int, target: str) -> str:
    return LOCATE_ELEMENT_PROMPT.format(width=width, height=height, target=target)
