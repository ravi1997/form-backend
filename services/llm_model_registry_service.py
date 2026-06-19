"""
services/llm_model_registry_service.py
Service for managing LLM models with versioning and A/B testing support.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
import uuid

from logger.unified_logger import app_logger, error_logger
from models.llm_model import LLMModel, LLMModelVersion
from utils.exceptions import ValidationError, NotFoundError


class ModelStatus(Enum):
    """Model status."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"
    TESTING = "testing"


class LLMModelRegistryService:
    """Service for managing LLM models with versioning and A/B testing."""

    def __init__(self):
        self._models_cache = {}  # Cache for active models
        self._last_cache_update = None

    async def register_model(
        self,
        provider: str,
        model_id: str,
        name: str,
        version: str,
        description: str = "",
        max_tokens: int = 4096,
        cost_per_1k_tokens: float = 0.0,
        supports_streaming: bool = False,
        supports_json: bool = False,
        parameters: Dict[str, Any] = None,
        tags: List[str] = None,
        organization_id: str = None,
        created_by: str = None
    ) -> LLMModel:
        """Register a new LLM model."""
        try:
            app_logger.info(f"Registering new LLM model: {model_id} v{version}")
            
            # Check if model with same provider and ID already exists
            existing_model = LLMModel.objects(
                provider=provider,
                model_id=model_id,
                is_deleted=False
            ).first()
            
            if existing_model:
                # Create new version instead
                return await self.create_model_version(
                    model_id=existing_model.id,
                    version=version,
                    max_tokens=max_tokens,
                    cost_per_1k_tokens=cost_per_1k_tokens,
                    supports_streaming=supports_streaming,
                    supports_json=supports_json,
                    parameters=parameters,
                    created_by=created_by
                )
            
            # Create new model
            model = LLMModel(
                provider=provider,
                model_id=model_id,
                name=name,
                description=description,
                max_tokens=max_tokens,
                cost_per_1k_tokens=cost_per_1k_tokens,
                supports_streaming=supports_streaming,
                supports_json=supports_json,
                parameters=parameters or {},
                tags=tags or [],
                organization_id=organization_id,
                created_by=created_by
            )
            model.save()
            
            # Create initial version
            await self.create_model_version(
                model_id=model.id,
                version=version,
                max_tokens=max_tokens,
                cost_per_1k_tokens=cost_per_1k_tokens,
                supports_streaming=supports_streaming,
                supports_json=supports_json,
                parameters=parameters,
                created_by=created_by
            )
            
            # Clear cache
            self._clear_cache()
            
            app_logger.info(f"Successfully registered LLM model: {model.id}")
            return model
            
        except Exception as e:
            error_logger.error(f"Failed to register LLM model: {str(e)}", exc_info=True)
            raise

    async def create_model_version(
        self,
        model_id: str,
        version: str,
        max_tokens: int = 4096,
        cost_per_1k_tokens: float = 0.0,
        supports_streaming: bool = False,
        supports_json: bool = False,
        parameters: Dict[str, Any] = None,
        created_by: str = None
    ) -> LLMModel:
        """Create a new version of an existing model."""
        try:
            app_logger.info(f"Creating new version {version} for model {model_id}")
            
            # Get model
            model = LLMModel.objects(id=model_id, is_deleted=False).first()
            if not model:
                raise NotFoundError(f"Model not found: {model_id}")
            
            # Check if version already exists
            existing_version = LLMModelVersion.objects(
                model_id=model_id,
                version=version,
                is_deleted=False
            ).first()
            
            if existing_version:
                raise ValidationError(f"Version {version} already exists for model {model_id}")
            
            # Create version
            model_version = LLMModelVersion(
                model_id=model_id,
                version=version,
                max_tokens=max_tokens,
                cost_per_1k_tokens=cost_per_1k_tokens,
                supports_streaming=supports_streaming,
                supports_json=supports_json,
                parameters=parameters or {},
                status=ModelStatus.TESTING.value,
                created_by=created_by
            )
            model_version.save()
            
            # Update model's current version if this is the first version
            if not model.current_version_id:
                model.current_version_id = model_version.id
                model.save()
            
            # Clear cache
            self._clear_cache()
            
            app_logger.info(f"Successfully created version {version} for model {model_id}")
            return model
            
        except Exception as e:
            error_logger.error(f"Failed to create model version: {str(e)}", exc_info=True)
            raise

    async def get_model(self, model_id: str, version: str = None) -> Dict[str, Any]:
        """Get model configuration by ID and optional version."""
        try:
            # Check cache first
            cache_key = f"{model_id}:{version or 'latest'}"
            if self._is_cache_valid() and cache_key in self._models_cache:
                return self._models_cache[cache_key]
            
            # Get model
            model = LLMModel.objects(model_id=model_id, is_deleted=False).first()
            if not model:
                raise NotFoundError(f"Model not found: {model_id}")
            
            # Get version
            if version:
                model_version = LLMModelVersion.objects(
                    model_id=model.id,
                    version=version,
                    is_deleted=False
                ).first()
            else:
                # Get current version
                model_version = LLMModelVersion.objects(
                    id=model.current_version_id,
                    is_deleted=False
                ).first()
            
            if not model_version:
                raise NotFoundError(f"Model version not found: {model_id} v{version}")
            
            # Build response
            result = {
                "id": str(model.id),
                "provider": model.provider,
                "model_id": model.model_id,
                "name": model.name,
                "description": model.description,
                "version": model_version.version,
                "max_tokens": model_version.max_tokens,
                "cost_per_1k_tokens": model_version.cost_per_1k_tokens,
                "supports_streaming": model_version.supports_streaming,
                "supports_json": model_version.supports_json,
                "parameters": model_version.parameters,
                "status": model_version.status,
                "tags": model.tags,
                "organization_id": str(model.organization_id) if model.organization_id else None,
                "created_at": model.created_at.isoformat(),
                "updated_at": model.updated_at.isoformat()
            }
            
            # Cache result
            if self._is_cache_valid():
                self._models_cache[cache_key] = result
            
            return result
            
        except Exception as e:
            error_logger.error(f"Failed to get model: {str(e)}", exc_info=True)
            raise

    async def list_models(
        self,
        provider: str = None,
        status: str = None,
        organization_id: str = None,
        tags: List[str] = None,
        page: int = 1,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """List models with filtering and pagination."""
        try:
            query = LLMModel.objects(is_deleted=False)
            
            if provider:
                query = query.filter(provider=provider)
            
            if organization_id:
                query = query.filter(organization_id=organization_id)
            
            if tags:
                query = query.filter(tags__all=tags)
            
            # Get total count
            total_count = query.count()
            
            # Apply pagination
            skip = (page - 1) * page_size
            models = query.skip(skip).limit(page_size)
            
            # Build response
            model_list = []
            for model in models:
                # Get current version
                current_version = None
                if model.current_version_id:
                    current_version = LLMModelVersion.objects(
                        id=model.current_version_id,
                        is_deleted=False
                    ).first()
                
                model_data = {
                    "id": str(model.id),
                    "provider": model.provider,
                    "model_id": model.model_id,
                    "name": model.name,
                    "description": model.description,
                    "current_version": current_version.version if current_version else None,
                    "status": current_version.status if current_version else ModelStatus.INACTIVE.value,
                    "tags": model.tags,
                    "created_at": model.created_at.isoformat(),
                    "updated_at": model.updated_at.isoformat()
                }
                
                model_list.append(model_data)
            
            return {
                "models": model_list,
                "total_count": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": (total_count + page_size - 1) // page_size
            }
            
        except Exception as e:
            error_logger.error(f"Failed to list models: {str(e)}", exc_info=True)
            raise

    async def activate_model_version(self, model_id: str, version: str, activated_by: str) -> Dict[str, Any]:
        """Activate a specific version of a model."""
        try:
            app_logger.info(f"Activating version {version} of model {model_id}")
            
            # Get model
            model = LLMModel.objects(model_id=model_id, is_deleted=False).first()
            if not model:
                raise NotFoundError(f"Model not found: {model_id}")
            
            # Get version
            model_version = LLMModelVersion.objects(
                model_id=model.id,
                version=version,
                is_deleted=False
            ).first()
            
            if not model_version:
                raise NotFoundError(f"Model version not found: {model_id} v{version}")
            
            # Deactivate all other versions
            LLMModelVersion.objects(
                model_id=model.id,
                is_deleted=False
            ).update(set__status=ModelStatus.INACTIVE.value)
            
            # Activate this version
            model_version.status = ModelStatus.ACTIVE.value
            model_version.activated_at = datetime.utcnow()
            model_version.activated_by = activated_by
            model_version.save()
            
            # Update model's current version
            model.current_version_id = model_version.id
            model.save()
            
            # Clear cache
            self._clear_cache()
            
            app_logger.info(f"Successfully activated version {version} of model {model_id}")
            return await self.get_model(model_id, version)
            
        except Exception as e:
            error_logger.error(f"Failed to activate model version: {str(e)}", exc_info=True)
            raise

    async def deprecate_model_version(self, model_id: str, version: str, deprecated_by: str) -> Dict[str, Any]:
        """Deprecate a specific version of a model."""
        try:
            app_logger.info(f"Deprecating version {version} of model {model_id}")
            
            # Get model
            model = LLMModel.objects(model_id=model_id, is_deleted=False).first()
            if not model:
                raise NotFoundError(f"Model not found: {model_id}")
            
            # Get version
            model_version = LLMModelVersion.objects(
                model_id=model.id,
                version=version,
                is_deleted=False
            ).first()
            
            if not model_version:
                raise NotFoundError(f"Model version not found: {model_id} v{version}")
            
            # Check if this is the current version
            if model.current_version_id == model_version.id:
                raise ValidationError("Cannot deprecate the currently active version")
            
            # Deprecate version
            model_version.status = ModelStatus.DEPRECATED.value
            model_version.deprecated_at = datetime.utcnow()
            model_version.deprecated_by = deprecated_by
            model_version.save()
            
            # Clear cache
            self._clear_cache()
            
            app_logger.info(f"Successfully deprecated version {version} of model {model_id}")
            return await self.get_model(model_id, version)
            
        except Exception as e:
            error_logger.error(f"Failed to deprecate model version: {str(e)}", exc_info=True)
            raise

    async def create_ab_test(
        self,
        model_id: str,
        test_name: str,
        versions: List[str],
        traffic_split: List[int],
        duration_days: int = 7,
        created_by: str = None
    ) -> Dict[str, Any]:
        """Create an A/B test for model versions."""
        try:
            app_logger.info(f"Creating A/B test {test_name} for model {model_id}")
            
            # Validate inputs
            if len(versions) != len(traffic_split):
                raise ValidationError("Number of versions must match traffic split")
            
            if sum(traffic_split) != 100:
                raise ValidationError("Traffic split must sum to 100")
            
            # Get model
            model = LLMModel.objects(model_id=model_id, is_deleted=False).first()
            if not model:
                raise NotFoundError(f"Model not found: {model_id}")
            
            # Validate versions exist
            for version in versions:
                model_version = LLMModelVersion.objects(
                    model_id=model.id,
                    version=version,
                    is_deleted=False
                ).first()
                
                if not model_version:
                    raise NotFoundError(f"Model version not found: {model_id} v{version}")
            
            # Create A/B test (simplified - in production, would have a separate ABTest model)
            ab_test_config = {
                "test_id": str(uuid.uuid4()),
                "test_name": test_name,
                "model_id": model_id,
                "versions": versions,
                "traffic_split": traffic_split,
                "duration_days": duration_days,
                "status": "active",
                "created_at": datetime.utcnow().isoformat(),
                "created_by": created_by,
                "ends_at": datetime.utcnow().replace(
                    hour=0, minute=0, second=0, microsecond=0
                ).replace(day=datetime.utcnow().day + duration_days).isoformat()
            }
            
            app_logger.info(f"Successfully created A/B test {test_name}")
            return ab_test_config
            
        except Exception as e:
            error_logger.error(f"Failed to create A/B test: {str(e)}", exc_info=True)
            raise

    async def get_model_versions(self, model_id: str) -> List[Dict[str, Any]]:
        """Get all versions of a model."""
        try:
            # Get model
            model = LLMModel.objects(model_id=model_id, is_deleted=False).first()
            if not model:
                raise NotFoundError(f"Model not found: {model_id}")
            
            # Get versions
            versions = LLMModelVersion.objects(
                model_id=model.id,
                is_deleted=False
            ).order_by("-created_at")
            
            version_list = []
            for version in versions:
                version_data = {
                    "id": str(version.id),
                    "version": version.version,
                    "max_tokens": version.max_tokens,
                    "cost_per_1k_tokens": version.cost_per_1k_tokens,
                    "supports_streaming": version.supports_streaming,
                    "supports_json": version.supports_json,
                    "status": version.status,
                    "created_at": version.created_at.isoformat(),
                    "activated_at": version.activated_at.isoformat() if version.activated_at else None,
                    "deprecated_at": version.deprecated_at.isoformat() if version.deprecated_at else None
                }
                
                version_list.append(version_data)
            
            return version_list
            
        except Exception as e:
            error_logger.error(f"Failed to get model versions: {str(e)}", exc_info=True)
            raise

    def _clear_cache(self):
        """Clear the models cache."""
        self._models_cache = {}
        self._last_cache_update = None

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if not self._last_cache_update:
            return False
        
        # Cache expires after 5 minutes
        cache_duration = 300  # seconds
        return (datetime.utcnow() - self._last_cache_update).total_seconds() < cache_duration

    async def warm_cache(self):
        """Warm up the cache with frequently used models."""
        try:
            app_logger.info("Warming up LLM models cache")
            
            # Get active models
            active_models = LLMModel.objects(is_deleted=False).filter(
                current_version_id__ne=None
            )
            
            for model in active_models:
                try:
                    await self.get_model(model.model_id)
                except Exception as e:
                    error_logger.warning(f"Failed to cache model {model.model_id}: {str(e)}")
            
            self._last_cache_update = datetime.utcnow()
            app_logger.info("Successfully warmed up LLM models cache")
            
        except Exception as e:
            error_logger.error(f"Failed to warm up cache: {str(e)}", exc_info=True)