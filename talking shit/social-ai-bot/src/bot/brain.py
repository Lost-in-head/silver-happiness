"""Bot brain: LLM + RAG + conversation memory."""

import os
from collections import deque

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from .prompt import build_system_prompt
from ..rag.store import RAGStore


class Bot:
    def __init__(
        self,
        rag: RAGStore,
        model: str = "gpt-4o-mini",
        memory_window: int = 10,
        llm_provider: str = "openai",
    ):
        self.rag = rag
        self.memory_window = memory_window
        self._history: deque[tuple[str, str]] = deque(maxlen=memory_window)
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required.")
        self.llm = ChatOpenAI(model=model, temperature=0.7, openai_api_key=api_key)

    def _build_messages(self, user_message: str, use_rag: bool = True) -> list:
        context = ""
        if use_rag:
            context = self.rag.retrieve(user_message)
        system = build_system_prompt(context)
        messages = [SystemMessage(content=system)]
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
        return content

    def clear_memory(self):
        self._history.clear()
