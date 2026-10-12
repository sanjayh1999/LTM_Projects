from __future__ import annotations

from functools import lru_cache

from langchain_core.language_models import BaseChatModel

from app.config import get_settings


@lru_cache
def get_llm() -> BaseChatModel:
    settings = get_settings()

    if settings.llm_provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(
            model=settings.llm_model or "llama3.1:8b",
            base_url=settings.ollama_base_url,
            temperature=0,
        )

    if settings.llm_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic(model=settings.llm_model, api_key=settings.anthropic_api_key)

    if settings.llm_provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=settings.llm_model, api_key=settings.openai_api_key)

    raise ValueError(f"Unknown LLM provider: {settings.llm_provider}")


if __name__ == "__main__":
    from langchain_core.tools import tool

    llm = get_llm()

    print("--- Basic invoke ---")
    print(llm.invoke("Say hello in one sentence.").content)

    @tool
    def get_weather(city: str) -> str:
        """Get the current weather for a given city."""
        return f"It's sunny in {city}."

    print("\n--- Tool-calling test ---")
    llm_with_tools = llm.bind_tools([get_weather])
    response = llm_with_tools.invoke("What's the weather in Paris? Use the tool to find out.")
    print("tool_calls:", response.tool_calls)