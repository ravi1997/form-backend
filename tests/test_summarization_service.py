from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services.summarization_service import SummarizationService


def _make_response(response_id, text, submitted_at):
    response = SimpleNamespace(
        id=response_id,
        submitted_at=submitted_at,
        data={"comment": text},
        get_decrypted_data=lambda: {"comment": text},
    )
    return response


@patch("services.summarization_service.FormResponse.objects")
def test_summarize_form_persists_snapshot(mock_objects):
    responses = [
        _make_response("resp-1", "The service is fast.", datetime(2026, 6, 1, tzinfo=timezone.utc)),
        _make_response("resp-2", "Support was helpful.", datetime(2026, 6, 2, tzinfo=timezone.utc)),
    ]
    mock_objects.return_value = responses

    service = SummarizationService()
    service.generate_executive_summary = MagicMock(return_value="summary text")
    service.save_summary_snapshot = MagicMock(return_value="snapshot-1")

    result = service.summarize_form("form-1")

    assert result == "summary text"
    service.generate_executive_summary.assert_called_once()
    service.save_summary_snapshot.assert_called_once()


def test_compare_summaries_returns_real_similarity_payload():
    service = SummarizationService()

    result = service.compare_summaries(
        "The response was fast and helpful",
        "The response was helpful and accurate",
    )

    assert result["provider"]
    assert result["comparison"]["score"] > 0
    assert "helpful" in result["comparison"]["overlap_terms"]
    assert "fast" in result["comparison"]["changed_terms"]
