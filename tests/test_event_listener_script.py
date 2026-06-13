from unittest.mock import patch

from scripts import event_listener


@patch("scripts.event_listener.start_consumers")
def test_event_listener_main_delegates_to_real_consumers(mock_start_consumers):
    event_listener.main()

    mock_start_consumers.assert_called_once()
