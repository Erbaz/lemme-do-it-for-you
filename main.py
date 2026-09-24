
from cmdln import StealthTerminal

def main():
    stealth = StealthTerminal("MyHiddenTerminal")
    stealth.spawn("python -m agent.master_agent")
    print("Agent launched in hidden terminal. Press Ctrl+C to stop.")


if __name__ == "__main__":
    main()