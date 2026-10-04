"""Configurable LLM provider factory.

Select the active provider with LLM_PROVIDER:
- groq
- openai
- anthropic
- ollama
"""

import os


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


def get_provider_name() -> str:
    return os.getenv("LLM_PROVIDER", "groq").strip().lower()


def get_required_api_key_name(provider: str | None = None) -> str | None:
    provider = (provider or get_provider_name()).lower()
    return {
        "groq": "GROQ_API_KEY",
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "ollama": None,
    }.get(provider)


def create_chat_model():
    """Create a LangChain chat model based on environment configuration."""
    provider = get_provider_name()
    temperature = _float_env("LLM_TEMPERATURE", 0.3)
    max_tokens = _int_env("LLM_MAX_TOKENS", 4096)

    if provider == "groq":
        try:
            from langchain_groq import ChatGroq
        except ImportError as exc:
            raise RuntimeError("Install langchain-groq to use LLM_PROVIDER=groq") from exc

        return ChatGroq(
            model=os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=os.getenv("GROQ_API_KEY"),
        )

    if provider == "openai":
        try:
            from langchain_openai import ChatOpenAI
        except ImportError as exc:
            raise RuntimeError("Install langchain-openai to use LLM_PROVIDER=openai") from exc

        return ChatOpenAI(
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=os.getenv("OPENAI_API_KEY"),
        )

    if provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:
            raise RuntimeError("Install langchain-anthropic to use LLM_PROVIDER=anthropic") from exc

        return ChatAnthropic(
            model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest"),
            temperature=temperature,
            max_tokens=max_tokens,
            api_key=os.getenv("ANTHROPIC_API_KEY"),
        )

    if provider == "ollama":
        try:
            from langchain_ollama import ChatOllama
        except ImportError as exc:
            raise RuntimeError("Install langchain-ollama to use LLM_PROVIDER=ollama") from exc

        return ChatOllama(
            model=os.getenv("OLLAMA_MODEL", "llama3.1"),
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            temperature=temperature,
        )

    raise ValueError(
        f"Unsupported LLM_PROVIDER={provider!r}. Use groq, openai, anthropic, or ollama."
    )

