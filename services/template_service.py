from typing import List
from logger import get_logger, audit_logger
from services.base import BaseService
from utils.exceptions import NotFoundError
from models import FormBlueprint, ProjectBlueprint, Form
from schemas.template import FormBlueprintSchema, ProjectBlueprintSchema
from schemas.base import InboundPayloadSchema

logger = get_logger(__name__)


class FormBlueprintCreateSchema(FormBlueprintSchema, InboundPayloadSchema):
    pass


class FormBlueprintUpdateSchema(FormBlueprintSchema, InboundPayloadSchema):
    pass


class FormBlueprintService(BaseService):
    def __init__(self):
        super().__init__(model=FormBlueprint, schema=FormBlueprintSchema)

    def list_official_blueprints(self) -> List[FormBlueprintSchema]:
        """Fetch curated, official market templates."""
        return self.list_all(is_official=True)

    def instantiate_blueprint(
        self, blueprint_id: str, organization_id: str, created_by: str
    ) -> Form:
        """
        Hydrates a new live Form from a Blueprint template.
        Copies structural definitions while initializing new tenant-specific state.
        """
        blueprint = self.model.objects(id=blueprint_id).first()
        if not blueprint:
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
            f"Instantiated new form {new_form.id} from blueprint {blueprint_id}"
        )
        return new_form


class ProjectBlueprintCreateSchema(ProjectBlueprintSchema, InboundPayloadSchema):
    pass


class ProjectBlueprintUpdateSchema(ProjectBlueprintSchema, InboundPayloadSchema):
    pass


class ProjectBlueprintService(BaseService):
    def __init__(self):
        super().__init__(model=ProjectBlueprint, schema=ProjectBlueprintSchema)
