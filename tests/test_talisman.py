import pytest
from app import create_app


@pytest.fixture
def app():
    app = create_app()
    app.config.update(
        {
            "TESTING": True,
            "DEBUG": False,  # Talisman headers are more active when DEBUG is False
        }
    )
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def test_security_headers(client):
    """Verify that Talisman security headers are present in the response."""
    response = client.get("/health")

    # Check for common Talisman headers
    assert "X-Frame-Options" in response.headers
    assert response.headers["X-Frame-Options"] == "DENY"

    assert "X-Content-Type-Options" in response.headers
    assert response.headers["X-Content-Type-Options"] == "nosniff"

    assert "X-XSS-Protection" in response.headers
    assert response.headers["X-XSS-Protection"] == "1; mode=block"

    assert "Content-Security-Policy" in response.headers
    assert "default-src" in response.headers["Content-Security-Policy"]

    # In non-DEBUG mode, HSTS should be present if force_https=True (or defaulted)
    # However, our app.py has force_https=False temporarily.
    # Let's check what we have.
