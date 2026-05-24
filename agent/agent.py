from llama_index.llms.ollama import Ollama
from llama_index.core.agent import ReActAgent
from llama_index.core.memory import ChatMemoryBuffer
from agent.tools import get_all_tools

class MasterAgent:
    """
    The Master ReAct Agent that orchestrates the execution of tasks.
    It uses a text-based LLM to reason and calls tools (including the Vision Agent) to interact.
    """
    def __init__(self, model_name: str = "llama3.1"):
        # We can use a strong text model for the master agent, e.g., llama3.1
        # Or if we want to stick to qwen, we can use a qwen text model.
        # Let's parameterize it. You can change this to your preferred local model.
        self.llm = Ollama(model=model_name, request_timeout=120.0)
        
        # Initialize memory buffer to keep track of chat history
        self.memory = ChatMemoryBuffer.from_defaults(token_limit=8000)
        
        # Load tools
        self.tools = get_all_tools()
        
        # Create ReAct Agent
        self.agent = ReActAgent.from_tools(
            tools=self.tools,
            llm=self.llm,
            memory=self.memory,
            verbose=True
        )

    def chat(self, user_input: str) -> str:
        """
        Sends a message to the agent and returns its response.
        """
        response = self.agent.chat(user_input)
        return str(response)

    def reset(self):
        """
        Resets the agent's memory.
        """
        self.memory.reset()
