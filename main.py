import sys
import pyautogui
from agent.agent import MasterAgent
from agent.vision_agent import VisionAgent, print_ollama_runtime_hint


def test_vision_agent():
    print("\n--- Testing Vision Agent ---")
    print("Taking screenshot...")
    screenshot_path = "test_screenshot.png"
    pyautogui.screenshot(screenshot_path)
    print(f"Screenshot saved to {screenshot_path}.")

    print("Initializing Vision Agent (qwen3-vl:8b)...")
    print("(First run may take several minutes while Ollama loads the model.)")
    try:
        vision_agent = VisionAgent(model_name="qwen3-vl:8b")
        screen_w, screen_h = pyautogui.size()
        target = "the close window button"
        print(f"Screen: {screen_w}x{screen_h} | Locating: {target}")
        print("Analyzing (first locate can take a few minutes)...")
        result = vision_agent.locate(target, screenshot_path)
        runtime = print_ollama_runtime_hint()
        if runtime:
            print(f"\n{runtime}")
        if isinstance(result, str):
            print(f"\nVision Analysis Result:\n{result}\n")
        else:
            print(
                f"\nLocate Result:\n"
                f"  Screen coordinates: ({result.x}, {result.y})\n"
                f"  Confidence: {result.confidence}\n"
                f"  Window: {result.window or 'n/a'}\n"
                f"  (Model saw {result.image_width}x{result.image_height}, "
                f"scaled to {result.screen_width}x{result.screen_height})\n"
                f"\nRaw model response:\n{result.raw_response}\n"
            )
    except Exception as e:
        print(f"Vision Agent Test Failed: {e}")


def run_master_agent():
    print("Initializing Lemme-Do-It-For-You Autonomous Agent...")
    print("Loading Master Agent (this might take a few seconds)...")

    # We use qwen3-vl:8b for the vision agent internally, but we can also use it for the master agent if it supports text-only well.
    # Alternatively, use a strong reasoning model like llama3.1 for the master. We'll default to llama3.1 for the text master.
    # You can change this if you want the master agent to also be qwen.
    try:
        agent = MasterAgent(model_name="llama3.1")
        print("Agent initialized successfully!")
    except Exception as e:
        print(f"Failed to initialize agent: {e}")
        sys.exit(1)

    print("\n--- Command Line Interface ---")
    print("Type your commands or tasks below. Type 'exit' or 'quit' to close.")

    while True:
        try:
            user_input = input("\nUser> ")
            if user_input.lower() in ["exit", "quit"]:
                print("Exiting...")
                break

            if not user_input.strip():
                continue

            print("Agent is thinking...")
            response = agent.chat(user_input)
            print(f"\nAgent> {response}")

        except KeyboardInterrupt:
            print("\nExiting...")
            break
        except Exception as e:
            print(f"\nError: {e}")


def main():
    print("Initializing Lemme-Do-It-For-You Autonomous Agent...")
    print("1. Test Vision Agent")
    print("2. Run Master Agent")
    choice = input("Select an option (1 or 2): ")

    if choice == "1":
        test_vision_agent()
    else:
        run_master_agent()


if __name__ == "__main__":
    main()
