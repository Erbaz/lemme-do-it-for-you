import os
from dotenv import load_dotenv
from llama_index.core import Settings

env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env')
load_dotenv(dotenv_path=env_path)

PROVIDER = (os.getenv("MODEL_PROVIDER") or "ollama").strip().lower()
MODEL_NAME = os.getenv("MODEL_NAME") or "qwen3-vl:8b-instruct"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL") or "http://localhost:11434"
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or ""
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL") or "https://openrouter.ai/api/v1"
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY") or ""
CONTEXT_WINDOW = int(os.getenv("CONTEXT_WINDOW") or "8192")
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT") or "120.0")
MAX_TOKENS = int(os.getenv("MAX_TOKENS") or "4096")

if PROVIDER == "openrouter":
    from llama_index.llms.openrouter import OpenRouter

    Settings.llm = OpenRouter(
        model=MODEL_NAME,
        api_key=OPENROUTER_API_KEY or OPENAI_API_KEY,
        api_base=OPENAI_BASE_URL,
        max_tokens=MAX_TOKENS,
        timeout=REQUEST_TIMEOUT,
        context_window=CONTEXT_WINDOW,
        additional_kwargs={
            "extra_body": {
                "reasoning": {
                    "effort": "none",
                }
            }
        },
    )
elif PROVIDER == "openai":
    from llama_index.llms.openai import OpenAI

    Settings.llm = OpenAI(
        model=MODEL_NAME,
        api_key=OPENAI_API_KEY,
        api_base=OPENAI_BASE_URL,
        max_tokens=MAX_TOKENS,
        timeout=REQUEST_TIMEOUT,
    )
else:
    from llama_index.llms.ollama import Ollama

    Settings.llm = Ollama(
        model=MODEL_NAME,
        base_url=OLLAMA_BASE_URL,
        request_timeout=REQUEST_TIMEOUT,
        context_window=CONTEXT_WINDOW,
    )


