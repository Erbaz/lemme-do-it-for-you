#!/usr/bin/env python3
"""
Diagnostic script to test the vision agent directly.
This will help identify if the issue is with:
1. The model not supporting vision
2. The image format
3. The API configuration
"""

import os
import sys
import traceback

# Add the project root to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_vision_agent():
    print("=" * 60)
    print("VISION AGENT DIAGNOSTIC TEST")
    print("=" * 60)

    # Test 1: Check environment variables
    print("\n[1] Checking environment variables...")
    from dotenv import load_dotenv
    load_dotenv()

    provider = os.getenv("MODEL_PROVIDER", "ollama")
    model_name = os.getenv("MODEL_NAME", "qwen3-vl:8b-instruct")
    print(f"    MODEL_PROVIDER: {provider}")
    print(f"    MODEL_NAME: {model_name}")

    # Test 2: Check model configuration
    print("\n[2] Checking model configuration...")
    try:
        import agent.model
        from llama_index.core import Settings
        llm = Settings.llm
        print(f"    LLM Type: {type(llm).__name__}")
        print(f"    LLM Model: {getattr(llm, 'model', 'N/A')}")

        # Check if it's OpenRouter
        if provider == "openrouter":
            print(f"    API Base: {getattr(llm, 'api_base', 'N/A')}")
            print(f"    Has API Key: {bool(getattr(llm, 'api_key', None))}")
    except Exception as e:
        print(f"    ERROR configuring model: {e}")
        traceback.print_exc()
        return

    # Test 3: Check if model supports vision
    print("\n[3] Checking if model supports vision...")
    if provider == "openrouter":
        print("    OpenRouter supports image inputs for multimodal models")
        print("    But the specific model may or may not support vision")
        if "vl" in model_name.lower() or "vision" in model_name.lower() or "qwen" in model_name.lower():
            print(f"    Model '{model_name}' appears to be a vision model (contains 'vl' or 'vision')")
        else:
            print(f"    WARNING: Model '{model_name}' may NOT be a vision model!")
    elif provider == "ollama":
        if "vl" in model_name.lower() or "vision" in model_name.lower():
            print(f"    Model '{model_name}' appears to be a vision model")
        else:
            print(f"    WARNING: Model '{model_name}' may NOT be a vision model!")
    else:
        print(f"    Provider '{provider}' - need to verify model supports vision")

    # Test 4: Create a test image
    print("\n[4] Creating test image...")
    try:
        from PIL import Image, ImageDraw
        import pyautogui

        # Create a simple test image (not a real screenshot, just for testing)
        img = Image.new('RGB', (800, 600), color=(70, 70, 70))
        draw = ImageDraw.Draw(img)
        draw.rectangle([50, 50, 200, 150], fill=(0, 120, 255))
        draw.text((60, 60), "Test Button", fill=(255, 255, 255))
        draw.ellipse([300, 200, 450, 350], fill=(0, 200, 100))
        img.save("test_image.png")
        print("    Test image created: test_image.png (800x600)")

        # Also create a real screenshot for comparison
        try:
            screenshot = pyautogui.screenshot()
            screenshot.save("test_screenshot.png")
            print(f"    Real screenshot created: test_screenshot.png ({screenshot.size[0]}x{screenshot.size[1]})")
        except Exception as e:
            print(f"    WARNING: Could not take screenshot: {e}")
    except Exception as e:
        print(f"    ERROR creating test image: {e}")
        traceback.print_exc()
        return

    # Test 5: Test vision agent with simple image
    print("\n[5] Testing vision agent with simple prompt...")
    try:
        from agent.self_correcting_vision_agent import SelfCorrectingVisionAgent

        agent = SelfCorrectingVisionAgent(verbose=True)
        print(f"    Vision agent initialized with model: {agent.model_name}")

        # Test with a very simple prompt
        print("\n    Sending test request to LLM...")
        response = agent.analyze_current_screen(
            prompt="Describe this image in one sentence.",
            screenshot_path="test_image.png"
        )
        print(f"\n    SUCCESS! Response: {response}")

    except Exception as e:
        print(f"\n    ERROR: {type(e).__name__}: {e}")
        print(f"    Full traceback:")
        traceback.print_exc()

    # Test 6: Check llama-index OpenRouter integration
    print("\n[6] Checking llama-index OpenRouter integration...")
    try:
        from llama_index.llms.openrouter import OpenRouter
        print("    OpenRouter class imported successfully")

        # Check if it supports image blocks
        import inspect
        sig = inspect.signature(OpenRouter.chat)
        print(f"    OpenRouter.chat signature: {sig}")

    except Exception as e:
        print(f"    ERROR: {e}")
        traceback.print_exc()

    print("\n" + "=" * 60)
    print("DIAGNOSTIC COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    test_vision_agent()