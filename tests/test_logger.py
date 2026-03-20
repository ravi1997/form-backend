import logging
from unittest.mock import patch
from logger.unified_logger import (
    error_logger,
    audit_logger,
    performance_logger,
    access_logger,
    app_logger,
    log_performance,
    PerformanceTimer,
    get_logger,
)


def test_logger_instances():
    """Test that all specified loggers are properly initialized."""
    assert error_logger.name == "error_logger"
    assert audit_logger.name == "audit_logger"
    assert performance_logger.name == "performance_logger"
    assert access_logger.name == "access_logger"
    assert app_logger.name == "application"


def test_get_logger():
    """Test getting a dynamic named logger."""
    test_log = get_logger("my_test_logger")
    assert test_log.name == "my_test_logger"


def test_sensitive_data_filter(caplog):
    """Test that sensitive information is successfully masked."""
    # Temporarily set up the test logger to use the console format or just catch it
    with caplog.at_level(logging.INFO):
        app_logger.info("User login successful with password: supersecret123")
        app_logger.info("This is a normal log.")

    # Due to how pytest's caplog captures logs, the filter modifies the record in-place but we can inspect it
    for record in caplog.records:
        if "MASKED" in record.msg:
            assert "supersecret123" not in record.msg
        else:
            assert "supersecret123" not in record.msg
            assert "normal log" in record.msg


@patch("logger.unified_logger.performance_logger.info")
def test_performance_decorator(mock_perf_info):
    """Test that the @log_performance decorator logs the function duration."""

    @log_performance
    def dummy_func():
        return "success"

    result = dummy_func()

    assert result == "success"
    assert mock_perf_info.called
    log_msg = mock_perf_info.call_args[0][0]
    assert "Function 'dummy_func'" in log_msg
    assert "took" in log_msg


@patch("logger.unified_logger.performance_logger.info")
def test_performance_timer_context(mock_perf_info):
    """Test the PerformanceTimer context manager."""
    with PerformanceTimer("db_query"):
        1 + 1

    assert mock_perf_info.called
    log_msg = mock_perf_info.call_args[0][0]
    assert "Block 'db_query'" in log_msg
    assert "took" in log_msg


def test_error_logger_output():
    """Check that error logger strictly logs errors."""
    error_logger.info(
        "This shouldn't be logged by default because error_logger level is ERROR"
    )
    error_logger.error("This is an actual error")
    # This verifies syntax doesn't crash, actual logging level tests can be done by checking handlers.
    assert error_logger.level == logging.ERROR
