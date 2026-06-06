import mongoengine
import mongomock
import pytest

from services.ai_model_registry_service import (
    PROMOTION_MIN_SCORE,
    AIModelRegistryService,
    ModelPromotionInput,
    ModelRollbackInput,
)
from services.exceptions import ValidationError
from models.ai_model_registry import AIModelRegistry


@pytest.fixture(scope="function")
def mock_db_conn():
    try:
        mongoengine.disconnect()
    except Exception:
        pass

    mongoengine.connect("test_model_registry_db", mongo_client_class=mongomock.MongoClient)
    yield
    try:
        mongoengine.disconnect()
    except Exception:
        pass


def test_promotion_gate_blocks_below_threshold(mock_db_conn):
    service = AIModelRegistryService()
    payload = ModelPromotionInput(
        organization_id="org-1",
        model_name="classifier",
        version="2026.06.01",
        evaluation_score=8.4,
        evaluation_details={"f1": 0.91},
    )

    with pytest.raises(ValidationError) as exc:
        service.promote(payload)

    assert str(PROMOTION_MIN_SCORE) in str(exc.value)
    assert AIModelRegistry.objects.count() == 0


def test_promotion_gate_allows_threshold_and_state_transitions(mock_db_conn):
    service = AIModelRegistryService()
    payload = ModelPromotionInput(
        organization_id="org-1",
        model_name="classifier",
        version="2026.06.01",
        evaluation_score=8.5,
        evaluation_details={"f1": 0.93},
        previous_version="2026.05.15",
    )

    registry = service.promote(payload)
    assert registry.status == AIModelRegistry.STATUS_PROMOTED
    assert registry.active_version == "2026.06.01"
    assert registry.previous_version == "2026.05.15"
    assert registry.evaluation_score == 8.5
    assert registry.promoted_at is not None

    activated = service.activate("org-1", "classifier", "2026.06.01")
    assert activated.status == AIModelRegistry.STATUS_ACTIVE
    assert activated.rollout_state == "active"
    assert activated.activated_at is not None

    held = service.hold("org-1", "classifier", "2026.06.01", "quality regression")
    assert held.status == AIModelRegistry.STATUS_HOLD
    assert held.rollback_reason == "quality regression"
    assert held.held_at is not None


def test_rollback_restores_state_and_records_target(mock_db_conn):
    service = AIModelRegistryService()
    promoted = service.promote(
        ModelPromotionInput(
            organization_id="org-1",
            model_name="classifier",
            version="2026.06.01",
            evaluation_score=9.1,
            evaluation_details={"precision": 0.97},
            previous_version="2026.05.15",
        )
    )
    service.activate("org-1", "classifier", "2026.06.01")

    rolled_back = service.rollback(
        ModelRollbackInput(
            organization_id="org-1",
            model_name="classifier",
            target_version="2026.05.15",
            reason="sla breach",
            active_version="2026.06.01",
        )
    )

    assert rolled_back.id == promoted.id
    assert rolled_back.status == AIModelRegistry.STATUS_ROLLED_BACK
    assert rolled_back.rollout_state == "rolled_back"
    assert rolled_back.rollback_target_version == "2026.05.15"
    assert rolled_back.rollback_reason == "sla breach"
    assert rolled_back.rolled_back_at is not None


def test_rollback_script_is_sla_compliant(mock_db_conn):
    service = AIModelRegistryService()
    script = service.create_rollback_script(
        organization_id="org-1",
        model_name="classifier",
        target_version="2026.05.15",
        reason="sla breach",
    )

    assert "#!/bin/sh" in script
    assert "set -eu" in script
    assert "rollback --organization-id" in script
    assert "classifier" in script
    assert "2026.05.15" in script
    assert "sla breach" in script
