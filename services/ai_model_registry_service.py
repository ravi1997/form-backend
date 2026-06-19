from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field

from logger.unified_logger import app_logger, audit_logger, error_logger
from models.ai import AIModelRegistry
from services.exceptions import ConflictError, NotFoundError, StateTransitionError, ValidationError


PROMOTION_MIN_SCORE = 8.5


class ModelPromotionInput(BaseModel):
    organization_id: str
    model_name: str
    version: str
    evaluation_score: float = Field(ge=0, le=10)
    evaluation_details: dict = Field(default_factory=dict)
    previous_version: str = ""


class ModelRollbackInput(BaseModel):
    organization_id: str
    model_name: str
    target_version: str
    reason: str
    active_version: Optional[str] = None


class AIModelRegistryService:
    def _get_registry(self, organization_id: str, model_name: str, version: str) -> AIModelRegistry:
        registry = AIModelRegistry.objects(
            organization_id=organization_id,
            model_name=model_name,
            version=version,
            is_deleted=False,
        ).first()
        if not registry:
            raise NotFoundError(
                f"Registry entry not found for {model_name} {version}",
                details={"organization_id": organization_id},
            )
        return registry

    def promote(self, payload: ModelPromotionInput) -> AIModelRegistry:
        app_logger.info(
            f"Promoting model {payload.model_name}:{payload.version} for org {payload.organization_id}"
        )
        try:
            if payload.evaluation_score < PROMOTION_MIN_SCORE:
                raise ValidationError(
                    f"Promotion blocked: evaluation score {payload.evaluation_score:.2f} is below {PROMOTION_MIN_SCORE:.1f}",
                    details={
                        "minimum_score": PROMOTION_MIN_SCORE,
                        "actual_score": payload.evaluation_score,
                    },
                )

            registry = AIModelRegistry.objects(
                organization_id=payload.organization_id,
                model_name=payload.model_name,
                version=payload.version,
            ).first()
            if registry and not registry.is_deleted:
                raise ConflictError(
                    "Model version already exists in the registry",
                    details={
                        "organization_id": payload.organization_id,
                        "model_name": payload.model_name,
                        "version": payload.version,
                    },
                )

            registry = registry or AIModelRegistry(
                organization_id=payload.organization_id,
                model_name=payload.model_name,
                version=payload.version,
            )
            registry.evaluation_score = payload.evaluation_score
            registry.evaluation_details = payload.evaluation_details
            registry.previous_version = payload.previous_version
            registry.mark_promoted(
                active_version=payload.version,
                previous_version=payload.previous_version,
            )
            registry.save()

            audit_logger.info(
                f"AUDIT: Model promoted {payload.model_name}:{payload.version} for org {payload.organization_id}"
            )
            return registry
        except Exception as exc:
            if isinstance(exc, (ValidationError, ConflictError)):
                raise
            error_logger.error(f"Failed to promote model: {exc}", exc_info=True)
            raise

    def activate(self, organization_id: str, model_name: str, version: str) -> AIModelRegistry:
        registry = self._get_registry(organization_id, model_name, version)
        if registry.status not in {
            AIModelRegistry.STATUS_PROMOTED,
            AIModelRegistry.STATUS_HOLD,
            AIModelRegistry.STATUS_ACTIVE,
        }:
            raise StateTransitionError(
                f"Cannot activate model from state '{registry.status}'",
                details={"status": registry.status},
            )
        registry.mark_active()
        registry.save()
        audit_logger.info(
            f"AUDIT: Model activated {model_name}:{version} for org {organization_id}"
        )
        return registry

    def hold(self, organization_id: str, model_name: str, version: str, reason: str) -> AIModelRegistry:
        registry = self._get_registry(organization_id, model_name, version)
        if registry.status not in {AIModelRegistry.STATUS_PROMOTED, AIModelRegistry.STATUS_ACTIVE}:
            raise StateTransitionError(
                f"Cannot place model on hold from state '{registry.status}'",
                details={"status": registry.status},
            )
        registry.mark_hold(reason=reason)
        registry.save()
        audit_logger.info(
            f"AUDIT: Model held {model_name}:{version} for org {organization_id}"
        )
        return registry

    def rollback(self, payload: ModelRollbackInput) -> AIModelRegistry:
        app_logger.info(
            f"Rolling back model {payload.model_name} to {payload.target_version} for org {payload.organization_id}"
        )
        registry = self._get_registry(
            payload.organization_id, payload.model_name, payload.active_version or payload.target_version
        )
        if registry.status not in {
            AIModelRegistry.STATUS_ACTIVE,
            AIModelRegistry.STATUS_PROMOTED,
            AIModelRegistry.STATUS_HOLD,
        }:
            raise StateTransitionError(
                f"Cannot rollback model from state '{registry.status}'",
                details={"status": registry.status},
            )
        registry.mark_rolled_back(target_version=payload.target_version, reason=payload.reason)
        registry.save()
        audit_logger.info(
            f"AUDIT: Model rolled back {payload.model_name} to {payload.target_version} for org {payload.organization_id}"
        )
        return registry

    def create_rollback_script(self, organization_id: str, model_name: str, target_version: str, reason: str) -> str:
        timestamp = datetime.now(timezone.utc).isoformat()
        return (
            "#!/bin/sh\n"
            "set -eu\n"
            f'echo "Rolling back {model_name} for org {organization_id} to {target_version}"\n'
            f'echo "reason={reason}"\n'
            f'echo "generated_at={timestamp}"\n'
            f'python -m services.ai_model_registry_service rollback --organization-id "{organization_id}" '
            f'--model-name "{model_name}" --target-version "{target_version}" --reason "{reason}"\n'
        )


ai_model_registry_service = AIModelRegistryService()
