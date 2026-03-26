from logger.unified_logger import app_logger, error_logger, audit_logger

class OllamaService:
    @staticmethod
    def health_check():
        app_logger.info("Performing Ollama health check")
        return {
            "status": "unavailable",
            "available": False,
            "models": [],
            "latency_ms": 0,
        }

    @staticmethod
    def get_default_model():
        app_logger.debug("Getting default Ollama model")
        return "llama3"

    @staticmethod
    def get_embedding_model():
        app_logger.debug("Getting Ollama embedding model")
        return "nomic-embed-text"

    @staticmethod
    def chat_stream(*args, **kwargs):
        app_logger.info("Initiating Ollama chat stream (stub)")
        yield {"content": "Ollama service unavailable (stub)", "done": True}

    @staticmethod
    def chat_stream_with_fallback(*args, **kwargs):
        app_logger.info("Initiating Ollama chat stream with fallback (stub)")
        yield {"content": "Ollama service unavailable (stub)", "done": True}

    @staticmethod
    def chat(*args, **kwargs):
        app_logger.info("Performing Ollama chat (stub)")
        return {"content": "Ollama service unavailable (stub)", "done": True}
