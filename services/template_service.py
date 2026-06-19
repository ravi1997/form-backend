"""
services/template_service.py
Service for managing form templates and blueprint creation.
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from mongoengine import Q
from logger.unified_logger import (
    app_logger,
    error_logger,
    audit_logger,
    get_logger,
    log_performance,
)
from services.base import BaseService
from utils.exceptions import NotFoundError, ValidationError, StateTransitionError
from models.form import Form, FormTemplate, Project
from models.form_commit import FormCommit
from models.identity import User
from schemas.template import FormBlueprintSchema

logger = get_logger(__name__)


class TemplateService(BaseService):
    """
    Service for managing form templates and blueprint creation.
    """

    def __init__(self):
        super().__init__(model=FormTemplate, schema=FormBlueprintSchema)

    def create_template_from_form(
        self,
        form_id: str,
        organization_id: str,
        template_data: Dict[str, Any],
        user_context: Dict[str, Any]
    ) -> FormBlueprintSchema:
        """
        Create a template from an existing form.
        
        Args:
            form_id: Source form ID
            organization_id: Organization ID
            template_data: Template metadata (name, description, category, etc.)
            user_context: User creating the template
            
        Returns:
            Created template
        """
        try:
            # Get the form
            form = Form.objects(
                id=form_id,
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if not form:
                raise NotFoundError("Form not found")
            
            # Get production commit for schema
            production_branch = getattr(form, 'production_branch', 'main')
            if not hasattr(form, 'branches') or production_branch not in form.branches:
                raise ValidationError("Form has no production version")
                
            commit_id = form.branches[production_branch]
            commit = FormCommit.objects(
                form_id=form_id,
                commit_id=commit_id,
                organization_id=organization_id
            ).first()
            
            if not commit:
                raise ValidationError("Form production version not found")
            
            # Prepare template data
            template_schema = {
                'name': template_data.get('name', f"Template from {form.name}"),
                'description': template_data.get('description', form.description),
                'category': template_data.get('category', 'General'),
                'tags': template_data.get('tags', []),
                'organization_id': organization_id,
                'is_public': template_data.get('is_public', False),
                'is_system': template_data.get('is_system', False),
                'schema': self._prepare_template_schema(commit.schema, form),
                'created_by': user_context.get('user_id'),
                'usage_count': 0
            }
            
            # Create template
            template = FormTemplate(**template_schema)
            template.save()
            
            audit_logger.info(
                f"AUDIT: Template created from form {form_id} by {user_context.get('user_id')}"
            )
            
            return self._to_schema(template)
            
        except Exception as e:
            error_logger.error(f"Failed to create template from form: {str(e)}", exc_info=True)
            raise

    def _prepare_template_schema(self, form_schema: Dict[str, Any], form: Form) -> Dict[str, Any]:
        """
        Prepare form schema for template use by removing form-specific data.
        """
        template_schema = form_schema.copy()
        
        # Remove form-specific access settings
        if 'access' in template_schema:
            template_schema['access'] = {
                'type': 'org',
                'allow_anonymous': False
            }
        
        # Remove form-specific settings
        if 'settings' in template_schema:
            template_schema['settings'] = {
                'allow_multiple_submissions': False,
                'allow_draft_save': True,
                'response_edit_policy': 'no_edit'
            }
        
        # Clear any form-specific IDs
        def _clear_ids(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key == 'id':
                        obj[key] = ''  # Clear ID for template
                    elif isinstance(value, (dict, list)):
                        _clear_ids(value)
            elif isinstance(obj, list):
                for item in obj:
                    _clear_ids(item)
        
        _clear_ids(template_schema)
        
        return template_schema

    def create_form_from_template(
        self,
        template_id: str,
        organization_id: str,
        form_data: Dict[str, Any],
        user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a new form from a template.
        
        Args:
            template_id: Template ID to use
            organization_id: Organization ID
            form_data: Form metadata (name, project_id, etc.)
            user_context: User creating the form
            
        Returns:
            Created form information
        """
        try:
            # Get template
            template = FormTemplate.objects(
                id=template_id,
                is_deleted=False
            ).first()
            
            if not template:
                raise NotFoundError("Template not found")
            
            # Check template access
            if not self._check_template_access(template, organization_id, user_context):
                raise ValidationError("You do not have access to this template")
            
            # Prepare form schema from template
            form_schema = self._prepare_form_schema(template.schema, form_data)
            
            # Create form
            from services.form_service import FormService
            form_service = FormService()
            
            form_create_data = {
                'name': form_data.get('name', template.name),
                'description': form_data.get('description', template.description),
                'organization_id': organization_id,
                'project_id': form_data.get('project_id'),
                'status': 'draft',
                'ui_config': form_schema.get('ui', {}),
                'access_policy': form_schema.get('access', {}),
                'submission_settings': form_schema.get('settings', {})
            }
            
            # Add sections from template
            sections_data = form_schema.get('sections', [])
            if sections_data:
                form_create_data['sections'] = sections_data
            
            form_schema_obj = form_service.FormCreateSchema(**form_create_data)
            form = form_service.create(form_schema_obj)
            
            # Increment template usage count
            template.usage_count += 1
            template.save()
            
            audit_logger.info(
                f"AUDIT: Form created from template {template_id} by {user_context.get('user_id')}"
            )
            
            return {
                'form_id': form.id,
                'form_name': form.name,
                'template_id': template_id,
                'template_name': template.name,
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            error_logger.error(f"Failed to create form from template: {str(e)}", exc_info=True)
            raise

    def _prepare_form_schema(self, template_schema: Dict[str, Any], form_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Prepare template schema for form creation by generating new IDs.
        """
        import uuid
        
        form_schema = template_schema.copy()
        
        # Generate new IDs for all elements
        def _generate_ids(obj):
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key == 'id':
                        obj[key] = str(uuid.uuid4())
                    elif isinstance(value, (dict, list)):
                        _generate_ids(value)
            elif isinstance(obj, list):
                for item in obj:
                    _generate_ids(item)
        
        _generate_ids(form_schema)
        
        # Update organization-specific settings
        if 'access' in form_schema:
            form_schema['access']['allowed_org_ids'] = [form_data.get('organization_id')]
        
        return form_schema

    def _check_template_access(
        self,
        template: FormTemplate,
        organization_id: str,
        user_context: Dict[str, Any]
    ) -> bool:
        """
        Check if user has access to use a template.
        """
        # System templates are accessible to everyone
        if template.is_system:
            return True
        
        # Public templates are accessible to everyone
        if template.is_public:
            return True
        
        # Organization templates are accessible to organization members
        if str(template.organization_id) == str(organization_id):
            return True
        
        return False

    def list_templates(
        self,
        organization_id: str,
        user_context: Dict[str, Any],
        category: str = None,
        is_public: bool = None,
        limit: int = 50,
        offset: int = 0
    ) -> List[FormBlueprintSchema]:
        """
        List available templates.
        
        Args:
            organization_id: Organization ID
            user_context: User context
            category: Filter by category
            is_public: Filter by public status
            limit: Maximum number of templates
            offset: Offset for pagination
            
        Returns:
            List of accessible templates
        """
        try:
            # Build query
            query = FormTemplate.objects(is_deleted=False)
            
            # Include system templates and public templates
            query = query.filter(
                Q(is_system=True) | 
                Q(is_public=True) | 
                Q(organization_id=organization_id)
            )
            
            # Apply filters
            if category:
                query = query.filter(category=category)
            
            if is_public is not None:
                query = query.filter(is_public=is_public)
            
            templates = query.order_by('-usage_count', '-created_at').skip(offset).limit(limit)
            
            # Filter based on access
            accessible_templates = []
            for template in templates:
                if self._check_template_access(template, organization_id, user_context):
                    accessible_templates.append(template)
            
            return [self._to_schema(template) for template in accessible_templates]
            
        except Exception as e:
            error_logger.error(f"Failed to list templates: {str(e)}", exc_info=True)
            raise

    def get_template(
        self,
        template_id: str,
        organization_id: str,
        user_context: Dict[str, Any]
    ) -> FormBlueprintSchema:
        """
        Get a specific template.
        
        Args:
            template_id: Template ID
            organization_id: Organization ID
            user_context: User context
            
        Returns:
            Template details
        """
        template = FormTemplate.objects(
            id=template_id,
            is_deleted=False
        ).first()
        
        if not template:
            raise NotFoundError("Template not found")
        
        # Check access
        if not self._check_template_access(template, organization_id, user_context):
            raise ValidationError("You do not have access to this template")
        
        return self._to_schema(template)

    def update_template(
        self,
        template_id: str,
        organization_id: str,
        update_data: Dict[str, Any],
        user_context: Dict[str, Any]
    ) -> FormBlueprintSchema:
        """
        Update template metadata.
        
        Args:
            template_id: Template ID
            organization_id: Organization ID
            update_data: Template updates
            user_context: User making updates
            
        Returns:
            Updated template
        """
        try:
            template = FormTemplate.objects(
                id=template_id,
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if not template:
                raise NotFoundError("Template not found")
            
            # Check if user can modify this template
            if not user_context.get('user_id') or str(template.created_by.id) != user_context.get('user_id'):
                # Check if user is org admin
                from services.form_permission_service import FormPermissionService
                perm_service = FormPermissionService()
                
                if not perm_service.check_form_access(
                    '',  # No form needed for template permission
                    organization_id,
                    user_context,
                    'admin'
                ):
                    raise ValidationError("You do not have permission to modify this template")
            
            # Update template
            update_schema = FormBlueprintSchema(**update_data)
            
            for field, value in update_schema.model_dump(exclude_unset=True).items():
                setattr(template, field, value)
            
            template.save()
            
            audit_logger.info(
                f"AUDIT: Template {template_id} updated by {user_context.get('user_id')}"
            )
            
            return self._to_schema(template)
            
        except Exception as e:
            error_logger.error(f"Failed to update template: {str(e)}", exc_info=True)
            raise

    def delete_template(
        self,
        template_id: str,
        organization_id: str,
        user_context: Dict[str, Any]
    ) -> None:
        """
        Delete a template.
        
        Args:
            template_id: Template ID
            organization_id: Organization ID
            user_context: User deleting the template
        """
        try:
            template = FormTemplate.objects(
                id=template_id,
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if not template:
                raise NotFoundError("Template not found")
            
            # Check if user can delete this template
            if not user_context.get('user_id') or str(template.created_by.id) != user_context.get('user_id'):
                # Check if user is org admin
                from services.form_permission_service import FormPermissionService
                perm_service = FormPermissionService()
                
                if not perm_service.check_form_access(
                    '',  # No form needed for template permission
                    organization_id,
                    user_context,
                    'admin'
                ):
                    raise ValidationError("You do not have permission to delete this template")
            
            # Soft delete
            template.is_deleted = True
            template.deleted_at = datetime.now(timezone.utc)
            template.save()
            
            audit_logger.info(
                f"AUDIT: Template {template_id} deleted by {user_context.get('user_id')}"
            )
            
        except Exception as e:
            error_logger.error(f"Failed to delete template: {str(e)}", exc_info=True)
            raise

    def create_project_template(
        self,
        project_id: str,
        organization_id: str,
        template_data: Dict[str, Any],
        user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Create a project template from an existing project.
        
        Args:
            project_id: Source project ID
            organization_id: Organization ID
            template_data: Template metadata
            user_context: User creating the template
            
        Returns:
            Created project template
        """
        try:
            # Get the project
            project = Project.objects(
                id=project_id,
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if not project:
                raise NotFoundError("Project not found")
            
            # Get all forms in the project
            forms = Form.objects(
                project=project,
                organization_id=organization_id,
                is_deleted=False
            )
            
            # Create template for each form
            form_templates = []
            for form in forms:
                form_template_data = {
                    'name': f"{template_data.get('name', project.name)} - {form.name}",
                    'description': form.description,
                    'category': template_data.get('category', 'Project'),
                    'tags': template_data.get('tags', []),
                    'is_public': template_data.get('is_public', False),
                    'is_system': False
                }
                
                form_template = self.create_template_from_form(
                    str(form.id),
                    organization_id,
                    form_template_data,
                    user_context
                )
                
                form_templates.append({
                    'form_name': form.name,
                    'template_id': form_template.id,
                    'template_name': form_template.name
                })
            
            return {
                'project_name': project.name,
                'form_templates': form_templates,
                'total_forms': len(form_templates),
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            error_logger.error(f"Failed to create project template: {str(e)}", exc_info=True)
            raise

    def get_template_categories(
        self,
        organization_id: str,
        user_context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Get all template categories with counts.
        
        Args:
            organization_id: Organization ID
            user_context: User context
            
        Returns:
            List of categories with template counts
        """
        try:
            # Get accessible templates
            templates = self.list_templates(
                organization_id,
                user_context,
                limit=1000  # Large limit to get all
            )
            
            # Count by category
            categories = {}
            for template in templates:
                category = template.category or 'Uncategorized'
                if category not in categories:
                    categories[category] = {
                        'name': category,
                        'count': 0
                    }
                categories[category]['count'] += 1
            
            # Sort by count
            return sorted(categories.values(), key=lambda x: x['count'], reverse=True)
            
        except Exception as e:
            error_logger.error(f"Failed to get template categories: {str(e)}", exc_info=True)
            raise

    def search_templates(
        self,
        organization_id: str,
        user_context: Dict[str, Any],
        query: str,
        category: str = None,
        limit: int = 20
    ) -> List[FormBlueprintSchema]:
        """
        Search templates by name, description, or tags.
        
        Args:
            organization_id: Organization ID
            user_context: User context
            query: Search query
            category: Filter by category
            limit: Maximum number of results
            
        Returns:
            List of matching templates
        """
        try:
            # Get all accessible templates
            templates = self.list_templates(
                organization_id,
                user_context,
                category=category,
                limit=1000
            )
            
            # Filter by search query
            query_lower = query.lower()
            matching_templates = []
            
            for template in templates:
                # Search in name, description, and tags
                if (query_lower in template.name.lower() or
                    query_lower in (template.description or '').lower() or
                    any(query_lower in tag.lower() for tag in (template.tags or []))):
                    matching_templates.append(template)
            
            return matching_templates[:limit]
            
        except Exception as e:
            error_logger.error(f"Failed to search templates: {str(e)}", exc_info=True)
            raise