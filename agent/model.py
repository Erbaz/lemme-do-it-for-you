from llama_index.llms.ollama import Ollama
from llama_index.core import Settings

    

Settings.llm = Ollama(model="qwen3-vl:8b-instruct", request_timeout=120.0, context_window=8192)


