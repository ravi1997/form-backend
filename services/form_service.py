from datetime import datetime, timezone
from typing import List
from logger.unified_logger import app_logger, error_logger, audit_logger, get_logger, log_performance
from logger.sla import enforce_sla
from services.base import BaseService
from utils.exceptions import NotFoundError, StateTransitionError
from models import Form, Project, Version, FormVersion
from schemas.form import FormSchema, ProjectSchema
from schemas.base import InboundPayloadSchema

logger = get_logger(__name__)


class FormCreateSchema(FormSchema, InboundPayloadSchema):
    pass


class FormUpdateSchema(FormSchema, InboundPayloadSchema):
    pass


from services.event_bus import event_bus


class FormService(BaseService):
    def __init__(self):
        super().__init__(model=Form, schema=FormSchema)

    @enforce_sla(max_ms=100)
    def create(self, create_schema: FormCreateSchema) -> FormSchema:
        app_logger.info(f"Entering FormService.create with title: {create_schema.title}")
        try:
            form = super().create(create_schema)
            event_bus.publish("form.indexed", form.model_dump())
            audit_logger.info(f"AUDIT: Form created with ID {form.id} and title {form.title}")
            app_logger.info(f"Successfully completed FormService.create for ID {form.id}")
            return form
        except Exception as e:
            error_logger.error(f"Error in FormService.create: {str(e)}", exc_info=True)
            raise

    def update(self, form_id: str, update_schema: FormUpdateSchema, organization_id: str = None) -> FormSchema:
        app_logger.info(f"Entering FormService.update for Form ID {form_id}")
        try:
            form = super().update(form_id, update_schema, organization_id=organization_id)
            event_bus.publish("form.indexed", form.model_dump())
            audit_logger.info(f"AUDIT: Form updated with ID {form_id}")
            app_logger.info(f"Successfully completed FormService.update for ID {form_id}")
            return form
        except Exception as e:
            error_logger.error(f"Error in FormService.update for ID {form_id}: {str(e)}", exc_info=True)
            raise

    @enforce_sla(max_ms=50)
    def get_by_slug(self, slug: str, organization_id: str) -> FormSchema:
        """Fetch form securely bounded by tenant slug."""
        app_logger.info(f"Entering get_by_slug: {slug} for org {organization_id}")
        try:
            form_doc = self.model.objects(
                slug=slug, organization_id=organization_id, is_deleted=False
            ).first()

            if not form_doc:
                app_logger.debug(f"Form '{slug}' not found in org {organization_id}")
                raise NotFoundError(f"Form '{slug}' not found")
            
            app_logger.info(f"Successfully completed get_by_slug for: {slug}")
            return self._to_schema(form_doc)
        except Exception as e:
            if not isinstance(e, NotFoundError):
                error_logger.error(f"Error in get_by_slug for {slug}: {str(e)}", exc_info=True)
            raise

    @log_performance
    def publish_form(
        self, form_id: str, organization_id: str = None, major_bump: bool = False, minor_bump: bool = True
    ) -> FormSchema:
        """
        Calculates Semantic Versioning and locks in an immutable snapshot
        (FormVersion) so active live forms are safe from structural breakage.
        """
        app_logger.info(f"Entering publish_form for Form ID {form_id}")
        filters = {'id': form_id, 'is_deleted': False}
        if organization_id:
            filters['organization_id'] = organization_id
            
        form_doc = self.model.objects(**filters).first()
        if not form_doc:
            app_logger.warning(f"Form {form_id} not found for publishing")
            raise NotFoundError("Form not found for publishing")

        try:
            # Semantic Version logic
            current_version = None
            if form_doc.active_version_id:
                current_version = Version.objects(id=form_doc.active_version_id).first()
            major, minor, patch = 1, 0, 0
            if current_version:
                major = (
                    current_version.major + 1 if major_bump else current_version.major
                )
                minor = (
                    current_version.minor + 1
                    if (minor_bump and not major_bump)
                    else (0 if major_bump else current_version.minor)
                )
                patch = (
                    current_version.patch + 1 if not (major_bump or minor_bump) else 0
                )

            # 1. Create the semantic map
            new_version = Version(form=form_doc, major=major, minor=minor, patch=patch)
            new_version.save()

            # 2. Extract an immutable snapshot, deep cloning sections as they exist right now
            snapshot = FormVersion(
                form=form_doc,
                version=new_version,
                status="published",
                sections=form_doc.sections if hasattr(form_doc, "sections") else [],
            )
            snapshot.save()

            # 3. Update active form
            form_doc.status = "published"
            form_doc.publish_at = datetime.now(timezone.utc)
            form_doc.active_version = new_version
            form_doc.save()

            audit_logger.info(
                f"AUDIT: Published '{form_doc.title}' at version v{major}.{minor}.{patch}"
            )
            app_logger.info(f"Successfully completed publish_form for ID {form_id}")
            return self._to_schema(form_doc)

        except Exception as e:
            error_logger.error(
                f"Failed to publish form {form_id}: {str(e)}", exc_info=True
            )
            raise StateTransitionError("Publish sequence failed", details=str(e))



class ProjectCreateSchema(ProjectSchema, InboundPayloadSchema):
    pass


class ProjectUpdateSchema(ProjectSchema, InboundPayloadSchema):
    pass


class ProjectService(BaseService):
    def __init__(self):
        super().__init__(model=Project, schema=ProjectSchema)

    def list_forms_in_project(self, project_id: str, organization_id: str = None) -> List[FormSchema]:
        """Deep queries safely resolved linked active forms in a project tree."""
        app_logger.info(f"Entering list_forms_in_project for Project ID {project_id}")
        try:
            filters = {'id': project_id, 'is_deleted': False}
            if organization_id:
                filters['organization_id'] = organization_id
                
            project_doc = self.model.objects(**filters).first()
            if not project_doc:
                app_logger.warning(f"Project {project_id} not found")
                raise NotFoundError("Project not found")

            # Extract safely avoiding dereferencing destroyed models
            forms = []
            for form in project_doc.forms:
                try:
                    if not form.is_deleted:
                        # Double check organization_id on the linked form
                        if organization_id and form.organization_id != organization_id:
                            continue
                        forms.append(FormSchema.model_validate(form.to_dict()))
                except Exception as e:
                    app_logger.warning(
                        f"Corrupt form pointer in project {project_id}: {str(e)}"
                    )

            app_logger.info(f"Successfully completed list_forms_in_project for Project ID {project_id}")
            return forms
        except Exception as e:
            if not isinstance(e, NotFoundError):
                error_logger.error(f"Error in list_forms_in_project for Project ID {project_id}: {str(e)}", exc_info=True)
            raise
