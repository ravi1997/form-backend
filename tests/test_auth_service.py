import pytest
from datetime import timedelta
from services.auth_service import AuthService
from utils.exceptions import UnauthorizedError
from models.User import User
from schemas.auth import TokenResponse


@pytest.fixture
def auth_service():
    return AuthService()


@pytest.fixture
def mock_user(monkeypatch):
    class MockUser:
        id = "507f1f77bcf86cd799439011"
        username = "testuser"
        roles = ["user"]
        is_active = True
        is_deleted = False

    return MockUser()


@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    class MockSettings:
        jwt_access_token_expires_minutes = 60
        jwt_refresh_token_expires_days = 30

    monkeypatch.setattr(
        "services.auth_service.SystemSettings.get_or_create_default",
        lambda: MockSettings(),
    )
    return MockSettings()


@pytest.fixture(autouse=True)
def mock_is_token_revoked(monkeypatch):
    monkeypatch.setattr(AuthService, "is_token_revoked", lambda self, jti: False)


def test_generate_tokens(auth_service, mock_user):
    tokens = auth_service.generate_tokens(mock_user)
    assert isinstance(tokens, TokenResponse)
    assert tokens.access_token is not None
    assert tokens.refresh_token is not None


def test_validate_token_success(auth_service, mock_user):
    tokens = auth_service.generate_tokens(mock_user)
    payload = auth_service.validate_token(tokens.access_token)
    assert payload.sub == str(mock_user.id)
    assert "user" in payload.roles


def test_validate_token_expired(auth_service, mock_user):
    # Create an already expired token
    token = auth_service.create_token(
        data={"sub": str(mock_user.id)}, expires_delta=timedelta(seconds=-1)
    )
    with pytest.raises(UnauthorizedError) as exc:
        auth_service.validate_token(token)
    assert "expired" in str(exc.value).lower()


def test_revoke_token(auth_service, mock_user, monkeypatch):
    tokens = auth_service.generate_tokens(mock_user)

    # Mock specifically for this test
    monkeypatch.setattr(AuthService, "is_token_revoked", lambda self, jti: True)

    with pytest.raises(UnauthorizedError) as exc:
        auth_service.validate_token(tokens.access_token)
    assert "revoked" in str(exc.value).lower()


def test_authenticate_user_failure(auth_service, monkeypatch):
    monkeypatch.setattr(User, "authenticate", lambda i, p: None)
    with pytest.raises(UnauthorizedError):
        auth_service.authenticate_user("wrong", "password")
