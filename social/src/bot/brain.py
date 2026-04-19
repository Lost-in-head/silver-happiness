"""Bot brain: LLM + RAG + conversation memory. Backed by OpenRouter (default) or Ollama."""

import logging
import os
from collections import deque

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from .prompt import build_system_prompt
from ..rag.store import RAGStore

logger = logging.getLogger(__name__)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_HEADERS = {
    "HTTP-Referer": "https://github.com/Lost-in-head/silver-happiness",
    "X-Title": "social",
}


def _build_llm(provider: str, model: str, temperature: float = 0.7):
    """
    Build a LangChain chat model.

    Supported providers:
      - openrouter (default): uses OPENROUTER_API_KEY env var
      - ollama: local; uses OLLAMA_BASE_URL env var (default http://localhost:11434)
    """
    provider = provider.lower().strip()

    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError:
            from langchain_community.chat_models import ChatOllama  # type: ignore[no-redef]
        base_url = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
        logger.info("Using Ollama provider at %s with model %s", base_url, model)
        return ChatOllama(model=model, base_url=base_url)

    # Default: OpenRouter
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError(
            "OPENROUTER_API_KEY environment variable is required for provider 'openrouter'. "
            "Get your key at https://openrouter.ai/keys"
        )
    logger.info("Using OpenRouter provider with model %s", model)
    return ChatOpenAI(
        model=model,
        temperature=temperature,
        openai_api_key=api_key,
        openai_api_base=OPENROUTER_BASE_URL,
        default_headers=OPENROUTER_HEADERS,
    )


class Bot:
    def __init__(
        self,
        rag: RAGStore,
        model: str = "openai/gpt-4o-mini",
        provider: str = "openrouter",
        memory_window: int = 10,
        top_k: int = 4,
        temperature: float = 0.7,
    ):
        self.rag = rag
        self.memory_window = memory_window
        self.top_k = top_k
        self._history: deque[tuple[str, str]] = deque(maxlen=memory_window)
        self.llm = _build_llm(provider, model, temperature)

    def _build_messages(self, user_message: str, use_rag: bool = True) -> list:
        context = ""
        if use_rag:
            context = self.rag.retrieve(user_message, top_k=self.top_k)
        system = build_system_prompt(context)
        messages: list = [SystemMessage(content=system)]
        for human, ai in self._history:
            messages.append(HumanMessage(content=human))
            messages.append(AIMessage(content=ai))
        messages.append(HumanMessage(content=user_message))
        return messages

    def ask(self, user_message: str, use_rag: bool = True) -> str:
        messages = self._build_messages(user_message, use_rag=use_rag)
        response = self.llm.invoke(messages)
        content = response.content if hasattr(response, "content") else str(response)
        self._history.append((user_message, content))
        logger.debug("Bot answered (rag=%s, history_len=%d)", use_rag, len(self._history))
        return content

    def clear_memory(self):
        self._history.clear()
        logger.debug("Bot memory cleared.")
