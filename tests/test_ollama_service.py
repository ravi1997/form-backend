from services.ollama_service import OllamaService


def test_ollama_chat_returns_unavailable_fallback():
    result = OllamaService.chat("hello")

    assert result == {"content": "Ollama service unavailable", "done": True}
