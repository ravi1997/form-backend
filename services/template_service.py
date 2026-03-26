from typing import List
from logger.unified_logger import app_logger, error_logger, audit_logger
from services.base import BaseService
from utils.exceptions import NotFoundError
from models import FormBlueprint, ProjectBlueprint, Form
from schemas.template import FormBlueprintSchema, ProjectBlueprintSchema
from schemas.base import InboundPayloadSchema


class FormBlueprintCreateSchema(FormBlueprintSchema, InboundPayloadSchema):
    pass


class FormBlueprintUpdateSchema(FormBlueprintSchema, InboundPayloadSchema):
    pass


class FormBlueprintService(BaseService):
    def __init__(self):
        super().__init__(model=FormBlueprint, schema=FormBlueprintSchema)

    def list_official_blueprints(self) -> List[FormBlueprintSchema]:
        """Fetch curated, official market templates."""
        app_logger.info("Listing official blueprints")
        try:
            blueprints = self.list_all(is_official=True)
            app_logger.info(f"Retrieved {len(blueprints)} official blueprints")
            return blueprints
        except Exception as e:
            error_logger.error(f"Error listing official blueprints: {e}", exc_info=True)
            raise

    def instantiate_blueprint(
        self, blueprint_id: str, organization_id: str, created_by: str
    ) -> Form:
        """
        Hydrates a new live Form from a Blueprint template.
        Copies structural definitions while initializing new tenant-specific state.
        """
        app_logger.info(f"Instantiating blueprint {blueprint_id} for organization {organization_id} by {created_by}")
        try:
            blueprint = self.model.objects(id=blueprint_id).first()
            if not blueprint:
                app_logger.warning(f"Blueprint template {blueprint_id} not found")
                raise NotFoundError("Blueprint template not found")

            # Create new Form from Blueprint structure
            new_form = Form(
                title=f"{blueprint.name} (Copy)",
                slug=f"{blueprint.name.lower().replace(' ', '-')}-copy",
                organization_id=organization_id,
                created_by=created_by,
                sections=blueprint.sections if hasattr(blueprint, "sections") else [],
                is_template=False,
                status="draft",
            )
            new_form.save()
            audit_logger.info(
                f"Instantiated new form {new_form.id} from blueprint {blueprint_id}",
                extra={
                    "event": "blueprint_instantiation",
                    "blueprint_id": blueprint_id,
                    "form_id": str(new_form.id),
                    "organization_id": organization_id,
                    "user_id": created_by
                }
            )
            app_logger.info(f"Successfully instantiated form {new_form.id} from blueprint {blueprint_id}")
            return new_form
        except NotFoundError:
            raise
        except Exception as e:
            error_logger.error(f"Error instantiating blueprint {blueprint_id}: {e}", exc_info=True)
            raise


class ProjectBlueprintCreateSchema(ProjectBlueprintSchema, InboundPayloadSchema):
    pass


class ProjectBlueprintUpdateSchema(ProjectBlueprintSchema, InboundPayloadSchema):
    pass


class ProjectBlueprintService(BaseService):
    def __init__(self):
        super().__init__(model=ProjectBlueprint, schema=ProjectBlueprintSchema)
        app_logger.info("ProjectBlueprintService initialized")
