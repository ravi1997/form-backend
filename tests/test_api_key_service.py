from datetime import datetime, timezone, timedelta

from models.ApiKey import ApiKey
from models.user import User
from services import api_key_service as api_key_service_module
from services.api_key_service import ApiKeyService


class _FakeRedisPipeline:
    def __init__(self, client):
        self.client = client

    def set(self, *args, **kwargs):
        self.client.set(*args, **kwargs)
        return self

    def execute(self):
        return None


class _FakeRedisClient:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set(self, key, value, ex=None):
        self.store[key] = value
        return True

    def pipeline(self):
        return _FakeRedisPipeline(self)


def _make_user():
    user = User(
        username="api-key-user",
        email="api-key-user@example.com",
        user_type="employee",
        organization_id="org-api",
        roles=["admin"],
        is_admin=True,
        is_active=True,
        is_deleted=False,
    )
    user.set_password("password123")
    user.save()
    return user


def test_create_validate_and_revoke_api_key(db_connection, monkeypatch):
    monkeypatch.setattr(
        api_key_service_module.redis_service.cache,
        "client",
        _FakeRedisClient(),
        raising=False,
    )
    user = _make_user()

    result = ApiKeyService.create_api_key(
        organization_id="org-api",
        name="Integration Key",
        created_by=user,
        scopes=["forms:write"],
    )

    assert result.raw_key.startswith("fbp_")
    assert result.record.key_prefix == result.prefix
    assert ApiKey.objects(id=result.record.id).first() is not None

    validated = ApiKeyService.get_active_key(result.raw_key, organization_id="org-api")
    assert validated is not None
    assert validated.id == result.record.id

    ApiKeyService.revoke_api_key(validated, revoked_by=user)
    assert ApiKeyService.get_active_key(result.raw_key, organization_id="org-api") is None


def test_api_key_rate_limit_trips_after_threshold(monkeypatch):
    fake_redis = _FakeRedisClient()
    monkeypatch.setattr(
        api_key_service_module.redis_service.cache,
        "client",
        fake_redis,
        raising=False,
    )
    monkeypatch.setattr(api_key_service_module, "API_KEY_RATE_LIMIT", 2)

    assert ApiKeyService.rate_limit_key("fbp_test_key_1") is True
    assert ApiKeyService.rate_limit_key("fbp_test_key_1") is True
    assert ApiKeyService.rate_limit_key("fbp_test_key_1") is False


def test_api_key_expires_when_past_due(db_connection, monkeypatch):
    monkeypatch.setattr(
        api_key_service_module.redis_service.cache,
        "client",
        _FakeRedisClient(),
        raising=False,
    )
    user = _make_user()
    result = ApiKeyService.create_api_key(
        organization_id="org-api",
        name="Expiring Key",
        created_by=user,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )

    assert ApiKeyService.get_active_key(result.raw_key, organization_id="org-api") is None
