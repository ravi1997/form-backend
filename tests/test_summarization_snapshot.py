from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from services.summarization_service import SummarizationService


@patch("services.summarization_service.SummarySnapshot")
def test_save_summary_snapshot_persists_snapshot(mock_snapshot_model):
    snapshot = MagicMock()
    snapshot.id = "snapshot-1"
    mock_snapshot_model.return_value = snapshot

    service = SummarizationService()
    result = service.save_summary_snapshot(
        form_id="form-1",
        period_start=datetime(2026, 6, 1, tzinfo=timezone.utc),
        period_end=datetime(2026, 6, 2, tzinfo=timezone.utc),
        summary_data={"bullet_points": ["A", "B"]},
        created_by="user-1",
        period_label="Responses 2",
        response_count=2,
        strategy_used="extractive_keyword_grouping",
    )

    assert result == "snapshot-1"
    mock_snapshot_model.assert_called_once()
    snapshot.save.assert_called_once()
