import platform
import asyncio
import agent.model
from llama_index.llms.ollama import Ollama
from llama_index.core import Settings
from llama_index.core.agent import ReActAgent
from llama_index.core.memory import Memory
from llama_index.core.workflow import Context
from llama_index.core.agent.workflow import AgentStream
from agent.tools import agent_tools

# SYS_PROMPT = f"""
#     You are a helpful Robotic Process Automation Agent. Your job is to call necessary tools to understand current state of GUI and execute steps to fulfill user instruction.
#     You are given a set of tools that you can use to interact with the computer.
#     Some of these tools have a vision agent behind them that will do as you instruct.
#     For example, if user asks you to "open the browser", you would have to use analyze_screen tool to ask vision agent to describe current screen state and identify if a Google Chrome icon is present. If tool response states that icon is present, then you would call move_mouse tool to ask the vision agent to move mouse to that icon. Once confirmed, you would use the relevant tool to mouse click and see if you can open the browser. You would confirm if task completed by analyzing screen through vision agent.
#     Sometimes moving the mouse may not be required at all. You have the execute_hotkey and press_key to commandeer. But to make sure you are aware of the changes in each step, rely on "analyze_screen" tool.
#     Always call analyze_screen after a mouse or keyboard event has taken place to understand what change has taken place, so that next step is made clear. For example, once you analyze the screen, you can identify where to move the mouse next or click at the current spot again.
#     Always confirm if user instruction is successfully accomplished by calling analyze_screen tool.
#     Follow the ReAct pattern to solve the task.
#     Current OS you will be working with: {platform.system()}
# """

SYS_PROMPT = f"""
You are a helpful Robotic Process Automation Agent. Your goal is to interpret user instructions, interact with the GUI, and execute the necessary steps to complete tasks.

### Core Operational Principles
* **Environment:** You are operating on {platform.system()}.
* **Methodology:** You must follow the **ReAct** (Reason + Act) pattern to solve tasks.
* **Vision-First Approach:** Some tools are powered by a vision agent. Always use the `analyze_screen` tool to verify the state of the GUI before and after taking actions.
* **State Verification:** Never assume an action succeeded. Always call `analyze_screen` after a mouse or keyboard event to confirm the state change and determine the next logical step.

### Interaction Workflow
1. **Analyze:** Call `analyze_screen` to understand the current environment and identify targets (e.g., icons, buttons).
2. **Execute:** Choose the appropriate tool based on the analysis.
    * Use `move_mouse` and click tools for visual interaction.
    * Use `execute_hotkey` or `press_key` for keyboard-based navigation when more efficient.
3. **Verify:** After any interaction, call `analyze_screen` again to confirm if the intended change occurred.
4. **Finalize:** Confirm to the user that the instruction has been successfully accomplished only after a final screen analysis verifies completion.

### Example Scenario: User instruction - Open the Chrome Browser
* **Step 1:** Call `analyze_screen` to verify if the Google Chrome icon is present.
* **Step 2:** If present, use `move_mouse` to target the icon.
* **Step 3:** If move_mouse tool responds with high confidence, perform the double click action. Else, try Step 2 with better prompting.
* **Step 4:** Call `analyze_screen` to confirm the browser has opened.
"""

class MasterAgent:
    """
    The Master ReAct Agent that orchestrates the execution of tasks.
    It uses a text-based LLM to reason and calls tools (including the Vision Agent) to interact.
    """
    def __init__(self, model_name: str = "qwen3-vl:4b-instruct"):
        # Or if we want to stick to qwen, we can use a qwen text model.
        # Let's parameterize it. You can change this to your preferred local model.
        self.llm = Settings.llm
        
        memory = Memory.from_defaults(session_id="my_session", token_limit=4096)


        
        # Load tools
        self.tools = agent_tools
        
        # Create ReAct Agent
        self.agent = ReActAgent(
            tools=self.tools,
            system_prompt=SYS_PROMPT,
            llm=self.llm,
            memory=memory,
            verbose=True
        )

        self.ctx = Context(self.agent)


    async def chat(self, user_input: str) -> str:
        """
        Sends a message to the agent and returns its response.
        """
        handler = self.agent.run(user_input, ctx=self.ctx)
        
        async for ev in handler.stream_events():
            # if isinstance(ev, ToolCallResult):
            #     print(f"\nCall {ev.tool_name} with {ev.tool_kwargs}\nReturned: {ev.tool_output}")
            if isinstance(ev, AgentStream):
                print(f"{ev.delta}", end="", flush=True)

        response = await handler
        return str(response)

    def reset(self):
        """
        Resets the agent's memory.
        """
        self.memory.reset()


if __name__ == "__main__":
    user_instruction = input("User: ")
    agent = MasterAgent()
    asyncio.run(agent.chat(user_instruction))