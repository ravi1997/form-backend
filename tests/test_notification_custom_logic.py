from services.notification_service import NotificationService


def test_run_custom_logic_evaluates_expression():
    result = NotificationService._run_custom_logic(
        "result = input_data['score'] > 7",
        {"score": 9},
    )

    assert result["result"] is True


def test_run_custom_logic_rejects_invalid_expression():
    result = NotificationService._run_custom_logic(
        "import os\nresult = os.listdir('/')",
        {"score": 9},
    )

    assert result["result"] is False
