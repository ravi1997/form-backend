"""
services/response_service.py
Service for handling form responses, validation, and submission logic.
"""

import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union
from mongoengine import Q
from logger.unified_logger import (
    app_logger,
    error_logger,
    audit_logger,
    get_logger,
    log_performance,
)
from logger.sla import enforce_sla
from services.base import BaseService
from services.form_service import FormService
from services.tenant_service import TenantService
from utils.exceptions import NotFoundError, ValidationError, StateTransitionError
from models.form import Form
from models.form_commit import FormCommit
from models.response import FormResponse, ResponseDraft, FileUpload
from models.identity import User
from schemas.response import FormResponseSchema

logger = get_logger(__name__)


class ResponseService(BaseService):
    """
    Service for handling form responses, including validation, submission,
    and draft management.
    """

    def __init__(self):
        super().__init__(model=FormResponse, schema=FormResponseSchema)
        self.form_service = FormService()

    def _validate_response_access(
        self, 
        form_id: str, 
        organization_id: str, 
        user_context: Dict[str, Any]
    ) -> bool:
        """
        Validate if the user has access to submit/view responses for this form.
        """
        try:
            # Get the production form version
            form = Form.objects(
                id=form_id,
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if not form:
                return False

            # Get production commit
            production_branch = getattr(form, 'production_branch', 'main')
            if not hasattr(form, 'branches') or production_branch not in form.branches:
                return False
                
            commit_id = form.branches[production_branch]
            commit = FormCommit.objects(
                form_id=form_id,
                commit_id=commit_id,
                organization_id=organization_id
            ).first()
            
            if not commit:
                return False

            # Evaluate access rules from schema
            access_config = commit.schema.get('access', {})
            access_type = access_config.get('type', 'org')
            
            if access_type == 'public':
                return True
                
            elif access_type == 'org':
                # Check if user belongs to the organization
                user_org_id = user_context.get('organization_id')
                return str(user_org_id) == str(organization_id)
                
            elif access_type == 'groups':
                # Check if user belongs to allowed groups
                allowed_group_ids = access_config.get('allowed_group_ids', [])
                user_group_ids = user_context.get('group_ids', [])
                return any(group_id in allowed_group_ids for group_id in user_group_ids)
                
            elif access_type == 'users':
                # Check if user is in allowed users list
                allowed_user_ids = access_config.get('allowed_user_ids', [])
                user_id = user_context.get('user_id')
                return str(user_id) in allowed_user_ids
                
            return False
            
        except Exception as e:
            logger.error(f"Failed to validate response access: {str(e)}", exc_info=True)
            return False

    def _validate_form_availability(self, form: Form) -> None:
        """
        Validate if the form is available for submissions.
        """
        # Check form status
        if form.status != 'published':
            raise ValidationError("Form is not published and not available for submissions")
        
        # Check expiration date
        if form.expires_at and form.expires_at < datetime.now(timezone.utc):
            raise ValidationError("Form has expired and is no longer accepting submissions")
        
        # Check submission limit
        if form.max_submissions:
            current_count = FormResponse.objects(
                form_id=form.id,
                status='submitted',
                is_deleted=False
            ).count()
            
            if current_count >= form.max_submissions:
                raise ValidationError("Form has reached maximum submission limit")

    def _validate_response_data(
        self, 
        form_commit: FormCommit, 
        response_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Validate response data against form schema.
        
        Returns:
            Validated and normalized response data
        """
        validated_data = {}
        schema = form_commit.schema
        
        # Validate sections and questions
        for section in schema.get('sections', []):
            section_id = section.get('id')
            if section_id not in response_data:
                continue
                
            validated_data[section_id] = {}
            section_responses = response_data[section_id]
            
            # Handle repeatable sections
            if isinstance(section_responses, list):
                for iteration_index, iteration_data in enumerate(section_responses):
                    validated_data[section_id][iteration_index] = self._validate_section_questions(
                        section, iteration_data, iteration_index
                    )
            else:
                validated_data[section_id] = self._validate_section_questions(
                    section, section_responses, 0
                )
        
        return validated_data

    def _validate_section_questions(
        self, 
        section: Dict[str, Any], 
        section_data: Dict[str, Any], 
        iteration_index: int
    ) -> Dict[str, Any]:
        """
        Validate questions within a section.
        """
        validated_questions = {}
        
        for question in section.get('questions', []):
            question_id = question.get('id')
            if question_id not in section_data:
                # Check if question is required
                if question.get('required', False):
                    raise ValidationError(f"Required question '{question.get('label')}' is missing")
                continue
                
            question_value = section_data[question_id]
            
            # Validate based on field type
            validated_value = self._validate_question_value(question, question_value)
            
            validated_questions[question_id] = {
                'value': validated_value,
                'display_value': str(validated_value),
                'answered_at': datetime.now(timezone.utc).isoformat(),
                'iteration_index': iteration_index
            }
            
            # Handle file uploads
            if question.get('field_type') in ['file_upload', 'image_capture']:
                if isinstance(question_value, list):
                    validated_questions[question_id]['file_ids'] = question_value
                elif isinstance(question_value, str):
                    validated_questions[question_id]['file_ids'] = [question_value]
        
        return validated_questions

    def _validate_question_value(
        self, 
        question: Dict[str, Any], 
        value: Any
    ) -> Any:
        """
        Validate a single question value based on its configuration.
        """
        field_type = question.get('field_type')
        
        # Check required fields
        if question.get('required', False) and (value is None or value == ''):
            raise ValidationError(f"Question '{question.get('label')}' is required")
        
        # Type-specific validation
        if field_type in ['text_input', 'text_area', 'email_input', 'url_input']:
            if value is not None and not isinstance(value, str):
                raise ValidationError(f"Question '{question.get('label')}' must be text")
            
            # Email validation
            if field_type == 'email_input' and value:
                import re
                email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
                if not re.match(email_pattern, value):
                    raise ValidationError(f"Invalid email format for '{question.get('label')}'")
        
        elif field_type in ['number_input', 'slider']:
            if value is not None:
                try:
                    numeric_value = float(value)
                    # Check min/max constraints
                    min_val = question.get('min_value')
                    max_val = question.get('max_value')
                    if min_val is not None and numeric_value < min_val:
                        raise ValidationError(f"Value must be at least {min_val}")
                    if max_val is not None and numeric_value > max_val:
                        raise ValidationError(f"Value must be at most {max_val}")
                    return numeric_value
                except (ValueError, TypeError):
                    raise ValidationError(f"Question '{question.get('label')}' must be a number")
        
        elif field_type in ['dropdown', 'radio_group', 'checkbox_group']:
            if value is not None:
                options = question.get('options', [])
                valid_values = [opt.get('value') for opt in options]
                
                if field_type == 'checkbox_group':
                    if not isinstance(value, list):
                        raise ValidationError(f"Question '{question.get('label')}' must be a list")
                    for v in value:
                        if v not in valid_values:
                            raise ValidationError(f"Invalid option '{v}' for '{question.get('label')}'")
                else:
                    if value not in valid_values:
                        raise ValidationError(f"Invalid option '{value}' for '{question.get('label')}'")
        
        elif field_type == 'checkbox':
            if value is not None and not isinstance(value, bool):
                raise ValidationError(f"Question '{question.get('label')}' must be true or false")
        
        return value

    @enforce_sla(max_ms=500)
    def create_response(
        self,
        form_id: str,
        organization_id: str,
        response_data: Dict[str, Any],
        user_context: Dict[str, Any] = None,
        is_draft: bool = False
    ) -> FormResponseSchema:
        """
        Create a new form response or draft.
        """
        try:
            app_logger.info(f"Creating response for form {form_id}")
            
            # Get form and validate access
            form = Form.objects(
                id=form_id,
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if not form:
                raise NotFoundError("Form not found")
            
            # Validate access permissions
            if not self._validate_response_access(form_id, organization_id, user_context or {}):
                raise ValidationError("You do not have permission to submit this form")
            
            # If not draft, validate form availability
            if not is_draft:
                self._validate_form_availability(form)
            
            # Get production commit for validation
            production_branch = getattr(form, 'production_branch', 'main')
            if not hasattr(form, 'branches') or production_branch not in form.branches:
                raise ValidationError("Form has no production version")
                
            commit_id = form.branches[production_branch]
            form_commit = FormCommit.objects(
                form_id=form_id,
                commit_id=commit_id,
                organization_id=organization_id
            ).first()
            
            if not form_commit:
                raise ValidationError("Form production version not found")
            
            # Validate response data
            validated_data = self._validate_response_data(form_commit, response_data)
            
            # Create response or draft
            if is_draft:
                response = self._create_draft(form, form_commit, validated_data, user_context)
            else:
                response = self._create_submission(form, form_commit, validated_data, user_context)
            
            audit_logger.info(
                f"AUDIT: {'Draft' if is_draft else 'Response'} created for form {form_id} "
                f"by {user_context.get('user_id', 'anonymous')}"
            )
            
            return response
            
        except Exception as e:
            error_logger.error(f"Failed to create response: {str(e)}", exc_info=True)
            raise

    def _create_draft(
        self,
        form: Form,
        form_commit: FormCommit,
        validated_data: Dict[str, Any],
        user_context: Dict[str, Any] = None
    ) -> FormResponseSchema:
        """
        Create a response draft.
        """
        # Check for existing draft
        existing_draft = ResponseDraft.objects(
            form_id=form.id,
            respondent_id=user_context.get('user_id') if user_context else None,
            organization_id=form.organization_id
        ).first()
        
        draft_data = {
            'form_id': form.id,
            'commit_id': form_commit.commit_id,
            'organization_id': form.organization_id,
            'respondent_id': user_context.get('user_id') if user_context else None,
            'partial_answers': validated_data,
            'last_saved_at': datetime.now(timezone.utc)
        }
        
        if existing_draft:
            # Update existing draft
            for key, value in draft_data.items():
                setattr(existing_draft, key, value)
            existing_draft.save()
            draft = existing_draft
        else:
            # Create new draft
            draft = ResponseDraft(**draft_data)
            draft.save()
        
        return self._schema_from_draft(draft)

    def _create_submission(
        self,
        form: Form,
        form_commit: FormCommit,
        validated_data: Dict[str, Any],
        user_context: Dict[str, Any] = None
    ) -> FormResponseSchema:
        """
        Create a form submission.
        """
        # Generate submission number
        submission_count = FormResponse.objects(
            form_id=form.id,
            is_deleted=False
        ).count()
        
        # Create response
        response_data = {
            'form_id': form.id,
            'commit_id': form_commit.commit_id,
            'organization_id': form.organization_id,
            'respondent_id': user_context.get('user_id') if user_context else None,
            'respondent_email': user_context.get('email') if user_context else None,
            'session_id': str(uuid.uuid4()),
            'status': 'submitted',
            'is_anonymous': not user_context.get('user_id'),
            'submission_number': submission_count + 1,
            'answers': validated_data,
            'repeat_groups': {},  # Will be populated if there are repeatable sections
            'metadata': {
                'ip_address': user_context.get('ip_address'),
                'user_agent': user_context.get('user_agent'),
                'device_type': user_context.get('device_type'),
                'platform': user_context.get('platform'),
                'started_at': user_context.get('started_at'),
                'completed_at': datetime.now(timezone.utc).isoformat(),
                'offline_submitted': user_context.get('offline_submitted', False)
            },
            'submitted_at': datetime.now(timezone.utc)
        }
        
        response = FormResponse(**response_data)
        response.save()
        
        # Delete any existing draft
        ResponseDraft.objects(
            form_id=form.id,
            respondent_id=user_context.get('user_id') if user_context else None,
            organization_id=form.organization_id
        ).delete()
        
        # Update tenant usage
        TenantService().record_response_submission(form.organization_id)
        
        return self._to_schema(response)

    def get_response(
        self,
        response_id: str,
        organization_id: str,
        user_context: Dict[str, Any] = None
    ) -> FormResponseSchema:
        """
        Get a specific response by ID.
        """
        response = FormResponse.objects(
            id=response_id,
            organization_id=organization_id,
            is_deleted=False
        ).first()
        
        if not response:
            raise NotFoundError("Response not found")
        
        # Check access permissions
        if not self._validate_response_access(str(response.form_id), organization_id, user_context or {}):
            raise ValidationError("You do not have permission to view this response")
        
        return self._to_schema(response)

    def list_responses(
        self,
        form_id: str,
        organization_id: str,
        user_context: Dict[str, Any] = None,
        limit: int = 50,
        offset: int = 0,
        status: str = None
    ) -> List[FormResponseSchema]:
        """
        List responses for a form.
        """
        # Validate access
        if not self._validate_response_access(form_id, organization_id, user_context or {}):
            raise ValidationError("You do not have permission to view responses for this form")
        
        query = FormResponse.objects(
            form_id=form_id,
            organization_id=organization_id,
            is_deleted=False
        ).order_by("-submitted_at")
        
        if status:
            query = query.filter(status=status)
        
        responses = query.skip(offset).limit(limit)
        
        return [self._to_schema(response) for response in responses]

    def update_response(
        self,
        response_id: str,
        update_data: Dict[str, Any],
        organization_id: str,
        user_context: Dict[str, Any] = None
    ) -> FormResponseSchema:
        """
        Update an existing response (if editing is allowed).
        """
        response = FormResponse.objects(
            id=response_id,
            organization_id=organization_id,
            is_deleted=False
        ).first()
        
        if not response:
            raise NotFoundError("Response not found")
        
        # Check if editing is allowed
        form = Form.objects(
            id=response.form_id,
            organization_id=organization_id,
            is_deleted=False
        ).first()
        
        if not form:
            raise NotFoundError("Form not found")
        
        # Check editing policy
        editing_policy = getattr(form, 'response_edit_policy', 'no_edit')
        if editing_policy == 'no_edit':
            raise ValidationError("This form does not allow response editing")
        
        # Validate access
        if not self._validate_response_access(str(response.form_id), organization_id, user_context or {}):
            raise ValidationError("You do not have permission to edit this response")
        
        # Get form commit for validation
        form_commit = FormCommit.objects(
            form_id=response.form_id,
            commit_id=response.commit_id,
            organization_id=organization_id
        ).first()
        
        if not form_commit:
            raise ValidationError("Form version not found")
        
        # Validate updated data
        validated_data = self._validate_response_data(form_commit, update_data)
        
        # Update response
        response.answers = validated_data
        response.metadata['completed_at'] = datetime.now(timezone.utc).isoformat()
        
        # Add to edit history
        if not hasattr(response, 'edit_history'):
            response.edit_history = []
        
        response.edit_history.append({
            'edited_at': datetime.now(timezone.utc).isoformat(),
            'edited_by': user_context.get('user_id'),
            'before': response.answers,
            'after': validated_data
        })
        
        response.save()
        
        audit_logger.info(
            f"AUDIT: Response {response_id} updated by {user_context.get('user_id')}"
        )
        
        return self._to_schema(response)

    def delete_response(
        self,
        response_id: str,
        organization_id: str,
        user_context: Dict[str, Any] = None
    ) -> None:
        """
        Delete a response.
        """
        response = FormResponse.objects(
            id=response_id,
            organization_id=organization_id,
            is_deleted=False
        ).first()
        
        if not response:
            raise NotFoundError("Response not found")
        
        # Validate access
        if not self._validate_response_access(str(response.form_id), organization_id, user_context or {}):
            raise ValidationError("You do not have permission to delete this response")
        
        # Soft delete
        response.is_deleted = True
        response.deleted_at = datetime.now(timezone.utc)
        response.save()
        
        audit_logger.info(
            f"AUDIT: Response {response_id} deleted by {user_context.get('user_id')}"
        )

    def get_draft(
        self,
        form_id: str,
        organization_id: str,
        user_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Get user's draft for a form.
        """
        draft = ResponseDraft.objects(
            form_id=form_id,
            respondent_id=user_context.get('user_id') if user_context else None,
            organization_id=organization_id
        ).first()
        
        if not draft:
            return {}
        
        return {
            'draft_id': str(draft.id),
            'form_id': str(draft.form_id),
            'partial_answers': draft.partial_answers,
            'last_saved_at': draft.last_saved_at.isoformat()
        }

    def _schema_from_draft(self, draft: ResponseDraft) -> FormResponseSchema:
        """
        Convert draft to schema.
        """
        return FormResponseSchema(
            id=str(draft.id),
            form_id=str(draft.form_id),
            commit_id=draft.commit_id,
            organization_id=draft.organization_id,
            respondent_id=str(draft.respondent_id) if draft.respondent_id else None,
            status='draft',
            answers=draft.partial_answers,
            created_at=draft.created_at,
            updated_at=draft.last_saved_at
        )

    def export_responses(
        self,
        form_id: str,
        organization_id: str,
        export_format: str = 'csv',
        user_context: Dict[str, Any] = None
    ) -> Dict[str, Any]:
        """
        Export responses for a form.
        """
        # Validate access
        if not self._validate_response_access(form_id, organization_id, user_context or {}):
            raise ValidationError("You do not have permission to export responses for this form")
        
        # Get all responses
        responses = FormResponse.objects(
            form_id=form_id,
            organization_id=organization_id,
            status='submitted',
            is_deleted=False
        ).order_by('submission_number')
        
        # Get form schema for field mapping
        form = Form.objects(
            id=form_id,
            organization_id=organization_id,
            is_deleted=False
        ).first()
        
        if not form:
            raise NotFoundError("Form not found")
        
        production_branch = getattr(form, 'production_branch', 'main')
        if not hasattr(form, 'branches') or production_branch not in form.branches:
            raise ValidationError("Form has no production version")
            
        commit_id = form.branches[production_branch]
        form_commit = FormCommit.objects(
            form_id=form_id,
            commit_id=commit_id,
            organization_id=organization_id
        ).first()
        
        if not form_commit:
            raise ValidationError("Form production version not found")
        
        # Generate export data
        export_data = {
            'form_id': form_id,
            'form_name': form.name,
            'export_format': export_format,
            'total_responses': responses.count(),
            'exported_at': datetime.now(timezone.utc).isoformat(),
            'data': []
        }
        
        for response in responses:
            response_data = {
                'response_id': str(response.id),
                'submission_number': response.submission_number,
                'submitted_at': response.submitted_at.isoformat(),
                'respondent_email': response.respondent_email,
                'ip_address': response.metadata.get('ip_address'),
                'user_agent': response.metadata.get('user_agent')
            }
            
            # Flatten answers
            for section_id, section_data in response.answers.items():
                for question_id, answer_data in section_data.items():
                    if isinstance(answer_data, dict):
                        response_data[f"{section_id}_{question_id}"] = answer_data.get('value')
                        response_data[f"{section_id}_{question_id}_display"] = answer_data.get('display_value')
            
            export_data['data'].append(response_data)
        
        return export_data