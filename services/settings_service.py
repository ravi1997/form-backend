from logger import get_logger, audit_logger
from services.base import BaseService
from utils.exceptions import ValidationError
from models import SystemSettings
from schemas.system_settings import SystemSettingsSchema
from schemas.base import InboundPayloadSchema

logger = get_logger(__name__)


class SystemSettingsUpdateSchema(SystemSettingsSchema, InboundPayloadSchema):
    pass


class SystemSettingsService(BaseService):
    def __init__(self):
        super().__init__(model=SystemSettings, schema=SystemSettingsSchema)

    def get_settings(self) -> SystemSettingsSchema:
        """
        Singleton pattern: Always return the global system configuration.
        Ensures a default configuration exists in MongoDB.
        """
        doc = SystemSettings.get_or_create_default()
        return self._to_schema(doc)

    def update_settings(
        self, update_schema: SystemSettingsUpdateSchema, updated_by: str
    ) -> SystemSettingsSchema:
        """
        Updates the global system configuration doc.
        Includes auditing of the administrative user performing the change.
        """
        doc = SystemSettings.get_or_create_default()

        # Enforce business logic constraints if any (e.g. min/max session times)
        update_data = update_schema.model_dump(exclude_unset=True)

        if "jwt_access_token_expires_minutes" in update_data:
            if not (1 <= update_data["jwt_access_token_expires_minutes"] <= 1440):
                raise ValidationError(
                    "Access token expiry must be between 1 and 1440 minutes"
                )

        # Perform atomic update
        doc.update(**{f"set__{k}": v for k, v in update_data.items()})
        doc.updated_by = updated_by
        doc.save()

        audit_logger.info(f"System settings updated by administrator: {updated_by}")
        doc.reload()
        return self._to_schema(doc)
