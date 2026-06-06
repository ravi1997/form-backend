import pytest
from flask_jwt_extended import create_access_token
from models.FeatureFlag import FeatureFlag
from services.feature_flag_service import FeatureFlagService
from utils.feature_gate import require_feature
from utils.response_helper import success_response
from utils.exceptions import NotFoundError

@pytest.fixture
def ff_service(redis_mock):
    FeatureFlag.objects.delete()
    # Explicitly clear Redis cache keys to prevent stale overrides from leaking
    from services.redis_service import redis_service
    try:
        redis_service.cache.client.flushdb()
    except Exception:
        pass
    service = FeatureFlagService()
    # Seed default flags
    service.seed_default_flags()
    return service

def test_seed_and_defaults(db_connection, ff_service, redis_mock):
    # Verify export_csv is enabled by default, others are disabled
    assert ff_service.is_feature_enabled("export_csv", "org_1") is True
    assert ff_service.is_feature_enabled("ai_classification", "org_1") is False

def test_global_update(db_connection, ff_service, redis_mock):
    # Enable ai_classification globally
    ff_service.update_global_flag("ai_classification", True)
    assert ff_service.is_feature_enabled("ai_classification", "org_1") is True

    # Disable export_csv globally
    ff_service.update_global_flag("export_csv", False)
    assert ff_service.is_feature_enabled("export_csv", "org_1") is False

def test_org_override(db_connection, ff_service, redis_mock):
    # Disable export_csv for org_1 only
    ff_service.set_org_override("export_csv", "org_1", False)
    assert ff_service.is_feature_enabled("export_csv", "org_1") is False
    assert ff_service.is_feature_enabled("export_csv", "org_2") is True  # still enabled globally

    # Enable ai_classification for org_2 only
    ff_service.set_org_override("ai_classification", "org_2", True)
    assert ff_service.is_feature_enabled("ai_classification", "org_2") is True
    assert ff_service.is_feature_enabled("ai_classification", "org_1") is False

def test_redis_cache_behavior(db_connection, ff_service, redis_mock):
    # Ensure cache is used and invalidated correctly
    # 1. Fetch to populate cache
    assert ff_service.is_feature_enabled("ai_classification", "org_cache") is False
    
    # 2. Modify DB record directly behind Service's back
    FeatureFlag.objects(flag_key="ai_classification").update_one(set__per_org_overrides={"org_cache": True})
    
    # 3. Check should still be False due to Redis Cache (60s TTL)
    assert ff_service.is_feature_enabled("ai_classification", "org_cache") is False
    
    # 4. Correctly update via Service, invalidating Cache
    ff_service.set_org_override("ai_classification", "org_cache", True)
    assert ff_service.is_feature_enabled("ai_classification", "org_cache") is True

def test_require_feature_decorator(db_connection, ff_service, redis_mock):
    from app import create_app
    from unittest.mock import patch
    from config.settings import settings
    # Override settings.MONGODB_URI to use the test container URI
    import os
    from unittest.mock import patch
    with patch("mongoengine.connect") as mock_connect:
        flask_app = create_app()
        client = flask_app.test_client()

        @flask_app.route("/test-feature")
        @require_feature("ai_classification")
        def dummy_route():
            return success_response(message="Success")

        # 1. Access without token -> 401
        resp = client.get("/test-feature")
        assert resp.status_code == 401

        # 2. Access with token but disabled flag -> 403
        with flask_app.app_context():
            token_disabled = create_access_token(
                identity="user1",
                additional_claims={"roles": ["user"], "organization_id": "org_blocked"}
            )
        resp = client.get("/test-feature", headers={"Authorization": f"Bearer {token_disabled}"})
        assert resp.status_code == 403

        # 3. Enable for this org
        ff_service.set_org_override("ai_classification", "org_allowed", True)
        from services.redis_service import redis_service
        redis_service.cache.client.flushdb()
        with flask_app.app_context():
            token_enabled = create_access_token(
                identity="user2",
                additional_claims={"roles": ["user"], "organization_id": "org_allowed"}
            )
        resp = client.get("/test-feature", headers={"Authorization": f"Bearer {token_enabled}"})
        assert resp.status_code == 200


        # 4. Superadmin bypasses gating entirely even if disabled
        with flask_app.app_context():
            token_sa = create_access_token(
                identity="sa",
                additional_claims={"roles": ["superadmin"], "organization_id": "system"}
            )
        resp = client.get("/test-feature", headers={"Authorization": f"Bearer {token_sa}"})
        assert resp.status_code == 200



def test_feature_flag_routes(db_connection, ff_service, redis_mock):
    from app import create_app
    from unittest.mock import patch
    with patch("mongoengine.connect") as mock_connect:
        flask_app = create_app()
        client = flask_app.test_client()

        with flask_app.app_context():
            superadmin_token = create_access_token(
                identity="sa",
                additional_claims={"roles": ["superadmin"], "organization_id": "system"}
            )
        headers_sa = {"Authorization": f"Bearer {superadmin_token}"}

        # 1. Get all flags
        resp = client.get("/mahasangraha/api/v1/admin/feature-flags/", headers=headers_sa)
        assert resp.status_code == 200
        data = resp.get_json()["data"]
        assert len(data) == 9

        # 2. Update global flag
        resp = client.put("/mahasangraha/api/v1/admin/feature-flags/ai_classification", json={"is_enabled": True}, headers=headers_sa)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["is_enabled"] is True

        # 3. Set org override
        resp = client.put("/mahasangraha/api/v1/admin/feature-flags/ai_classification/override/tesla", json={"is_enabled": False}, headers=headers_sa)
        assert resp.status_code == 200
        assert resp.get_json()["data"]["per_org_overrides"]["tesla"] is False


def test_feature_flag_cache_metrics(db_connection, ff_service, redis_mock):
    # Reset/flush metrics
    from services.redis_service import redis_service
    redis_service.cache.client.delete("metrics:feature_flag:hits", "metrics:feature_flag:misses")

    # 1. Initially metrics should be zero
    metrics = ff_service.get_cache_metrics()
    assert metrics["hits"] == 0
    assert metrics["misses"] == 0
    assert metrics["total"] == 0
    assert metrics["hit_rate_percent"] == 0.0

    # 2. Check feature flag (should miss)
    ff_service.is_feature_enabled("export_csv", "org_metrics")
    metrics = ff_service.get_cache_metrics()
    assert metrics["hits"] == 0
    assert metrics["misses"] == 1
    assert metrics["total"] == 1
    assert metrics["hit_rate_percent"] == 0.0

    # 3. Check feature flag again (should hit)
    ff_service.is_feature_enabled("export_csv", "org_metrics")
    metrics = ff_service.get_cache_metrics()
    assert metrics["hits"] == 1
    assert metrics["misses"] == 1
    assert metrics["total"] == 2
    assert metrics["hit_rate_percent"] == 50.0



