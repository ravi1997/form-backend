class OllamaService:
    @staticmethod
    def health_check():
        return {
            "status": "unavailable",
            "available": False,
            "models": [],
            "latency_ms": 0,
        }

    @staticmethod
    def get_default_model():
        return "llama3"

    @staticmethod
    def get_embedding_model():
        return "nomic-embed-text"

    @staticmethod
    def chat_stream(*args, **kwargs):
        yield {"content": "Ollama service unavailable (stub)", "done": True}

    @staticmethod
    def chat_stream_with_fallback(*args, **kwargs):
        yield {"content": "Ollama service unavailable (stub)", "done": True}

    @staticmethod
    def chat(*args, **kwargs):
        return {"content": "Ollama service unavailable (stub)", "done": True}
