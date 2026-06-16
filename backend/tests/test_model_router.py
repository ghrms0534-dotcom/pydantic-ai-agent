from backend.app.agent.model_router import select_model
from backend.app.config import get_settings


def test_chat_intent_selects_fast_model(monkeypatch) -> None:
    monkeypatch.setenv("FAST_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("OLLAMA_MODEL", "fallback:model")
    get_settings.cache_clear()

    assert select_model("chat", "Chat Agent", "selection") == "qwen2.5:3b"

    get_settings.cache_clear()


def test_k8s_tool_intent_selects_fast_model(monkeypatch) -> None:
    monkeypatch.setenv("FAST_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("OLLAMA_MODEL", "fallback:model")
    get_settings.cache_clear()

    assert select_model("k8s", "Tool Agent", "execution") == "qwen2.5:3b"

    get_settings.cache_clear()


def test_validation_selects_reasoning_model(monkeypatch) -> None:
    monkeypatch.setenv("REASONING_MODEL", "deepseek-r1:1.5b")
    monkeypatch.setenv("OLLAMA_MODEL", "fallback:model")
    get_settings.cache_clear()

    assert select_model("k8s", "Validator Agent", "validation") == "deepseek-r1:1.5b"

    get_settings.cache_clear()


def test_final_answer_selects_korean_model(monkeypatch) -> None:
    monkeypatch.setenv("KOREAN_MODEL", "gemma3:4b")
    monkeypatch.setenv("OLLAMA_MODEL", "fallback:model")
    get_settings.cache_clear()

    assert select_model("chat", "Summary Agent", "summary") == "gemma3:4b"

    get_settings.cache_clear()


def test_missing_model_env_falls_back_to_ollama_model(monkeypatch) -> None:
    monkeypatch.delenv("FAST_MODEL", raising=False)
    monkeypatch.delenv("KOREAN_MODEL", raising=False)
    monkeypatch.delenv("REASONING_MODEL", raising=False)
    monkeypatch.setenv("OLLAMA_MODEL", "fallback:model")
    get_settings.cache_clear()

    assert select_model("chat", "Chat Agent", "selection") == "fallback:model"
    assert select_model("chat", "Summary Agent", "summary") == "fallback:model"
    assert select_model("chat", "Validator Agent", "validation") == "fallback:model"

    get_settings.cache_clear()
