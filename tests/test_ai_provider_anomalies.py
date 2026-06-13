from services.ai_provider import LocalHeuristicProvider, OllamaProvider


def test_local_provider_detects_basic_anomalies():
    provider = LocalHeuristicProvider()
    anomalies = provider.detect_anomalies(
        [
            {"name": "Test", "score": -1, "note": "N/A"},
            "not-a-dict",
        ]
    )

    assert len(anomalies) == 2
    assert anomalies[0]["issues"]
    assert anomalies[1]["issue"] == "non_object_record"


def test_ollama_provider_uses_same_heuristic_scan():
    provider = OllamaProvider(base_url="http://localhost:11434")
    anomalies = provider.detect_anomalies([{"status": "sample"}])

    assert anomalies[0]["issues"][0]["issue"] == "suspicious_placeholder"
