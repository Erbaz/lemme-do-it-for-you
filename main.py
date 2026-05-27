
# from llama_index.core.agent.workflow import ReActAgent
# from llama_index.core.workflow import Context
# from llama_index.llms.ollama import Ollama
# from llama_index.core.tools import FunctionTool

# # 1. Define Tools
# def add(a: int, b: int) -> int:
#     """Add two integers and returns the result."""
#     return a + b

# # 2. Define the LLM (Using a smaller model to avoid OOM)
# llm = Ollama(model="qwen3-vl:4b-instruct")

# # 3. Standard Initialization
# # Note: In the workflow version, we don't pass 'memory' directly to the constructor
# # as the workflow handles session state via the Context object.
# agent = ReActAgent(tools=[FunctionTool.from_defaults(fn=add)], llm=llm)

# # 4. Create Context
# ctx = Context(agent)

# # 5. Run via Workflow
# async def main():
#     handler = agent.run("What is 5+3?", ctx=ctx)
#     # The handler manages the event stream
#     async for ev in handler.stream_events():
#         # Handle events as needed
#         pass
#     result = await handler
#     print(f"Result: {result}")

# import asyncio
# if __name__ == "__main__":
#     asyncio.run(main())


import ollama
import time

def test_inference(model_name="qwen3-vl:4b-instruct"):
    print(f"Testing {model_name}...")
    
    start_time = time.time()
    
    # Simple generate call
    response = ollama.generate(model=model_name, prompt="Why is the sky blue? Answer in one sentence.")
    
    end_time = time.time()
    
    print(f"\nResponse: {response['response']}")
    print(f"\nTime taken: {end_time - start_time:.2f} seconds")

if __name__ == "__main__":
    test_inference()