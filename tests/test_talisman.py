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


def test_cors_allows_flutter_dev_origin(client):
    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:51337",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:51337"
    assert response.headers["Access-Control-Allow-Credentials"] == "true"


def test_waf_tolerates_nested_hex_colors_but_blocks_sqli(client):
    # 1. Legitimate nested hex color should be allowed (will hit 404 because form isn't real, but not 403 WAF block)
    response = client.put(
        "/mahasangraha/api/v1/projects/ba4aeb2c-83c2-4c84-b9b2-e7713d64f8eb/forms/c700ae23-44d3-4ce6-a804-2a2146cc3d99/draft",
        json={"sections": [{"style": {"backgroundColor": "#FFFFFF"}}]},
        headers={"X-Organization-ID": "org_001"},
    )
    # WAF did not block it with 403, so it processed past it (may fail with 401 auth or 404, but NOT 403)
    assert response.status_code != 403

    # 2. SQL Injection in a normal field should be blocked with 403
    response = client.put(
        "/mahasangraha/api/v1/projects/ba4aeb2c-83c2-4c84-b9b2-e7713d64f8eb/forms/c700ae23-44d3-4ce6-a804-2a2146cc3d99/draft",
        json={
            "sections": [
                {
                    "title": "Legit Title",
                    "description": "normal text OR 1=1 -- SQLi test",
                }
            ]
        },
        headers={"X-Organization-ID": "org_001"},
    )
    assert response.status_code == 403
