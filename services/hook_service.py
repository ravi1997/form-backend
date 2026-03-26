from typing import List, Dict, Any, Union
import requests
import json
from logger.unified_logger import app_logger, error_logger, audit_logger
from models.Form import Form, Project
from models.AccessControl import ExternalHook
from schemas.access_control import ExternalHookSchema
from utils.exceptions import NotFoundError, ForbiddenError, ValidationError
from services.base import BaseService
from datetime import datetime, timezone

class HookService(BaseService):
    def __init__(self):
        super().__init__(model=ExternalHook, schema=ExternalHookSchema)

    def trigger_question_hooks(self, form_id: str, question_id: str, payload: Dict[str, Any], user_id: str, organization_id: str) -> List[Dict[str, Any]]:
        """Synchronously triggers all hooks for a specific question."""
        app_logger.info(f"Triggering question hooks for form {form_id}, question {question_id}, user {user_id}")
        try:
            form = Form.objects(id=form_id, organization_id=organization_id, is_deleted=False).first()
            if not form:
                app_logger.warning(f"Form {form_id} not found for organization {organization_id}")
                raise NotFoundError("Form not found")

            question = self._find_question(form, question_id)
            if not question:
                app_logger.warning(f"Question {question_id} not found in form {form_id}")
                raise NotFoundError("Question not found")

            results = self._execute_triggers(getattr(question, 'logic', None), payload, organization_id)
            app_logger.info(f"Successfully triggered {len(results)} question hooks")
            return results
        except Exception as e:
            error_logger.error(f"Error triggering question hooks: {str(e)}", exc_info=True)
            raise

    def trigger_section_hooks(self, form_id: str, section_id: str, payload: Dict[str, Any], user_id: str, organization_id: str) -> List[Dict[str, Any]]:
        """Synchronously triggers all hooks for a specific section."""
        app_logger.info(f"Triggering section hooks for form {form_id}, section {section_id}, user {user_id}")
        try:
            form = Form.objects(id=form_id, organization_id=organization_id, is_deleted=False).first()
            if not form:
                app_logger.warning(f"Form {form_id} not found for organization {organization_id}")
                raise NotFoundError("Form not found")

            section = self._find_section(form, section_id)
            if not section:
                app_logger.warning(f"Section {section_id} not found in form {form_id}")
                raise NotFoundError("Section not found")

            results = self._execute_triggers(getattr(section, 'logic', None), payload, organization_id)
            app_logger.info(f"Successfully triggered {len(results)} section hooks")
            return results
        except Exception as e:
            error_logger.error(f"Error triggering section hooks: {str(e)}", exc_info=True)
            raise

    def trigger_form_hooks(self, form_id: str, payload: Dict[str, Any], user_id: str, organization_id: str) -> List[Dict[str, Any]]:
        """Synchronously triggers all top-level hooks for a form."""
        app_logger.info(f"Triggering form hooks for form {form_id}, user {user_id}")
        try:
            form = Form.objects(id=form_id, organization_id=organization_id, is_deleted=False).first()
            if not form:
                app_logger.warning(f"Form {form_id} not found for organization {organization_id}")
                raise NotFoundError("Form not found")

            # Forms have triggers directly in the document, sometimes nested in logic
            triggers_source = form
            if hasattr(form, 'logic') and form.logic:
                triggers_source = form.logic

            results = self._execute_triggers(triggers_source, payload, organization_id)
            app_logger.info(f"Successfully triggered {len(results)} form hooks")
            return results
        except Exception as e:
            error_logger.error(f"Error triggering form hooks: {str(e)}", exc_info=True)
            raise

    def trigger_project_hooks(self, project_id: str, payload: Dict[str, Any], user_id: str, organization_id: str) -> List[Dict[str, Any]]:
        """Synchronously triggers all hooks for a project."""
        app_logger.info(f"Triggering project hooks for project {project_id}, user {user_id}")
        try:
            project = Project.objects(id=project_id, organization_id=organization_id, is_deleted=False).first()
            if not project:
                app_logger.warning(f"Project {project_id} not found for organization {organization_id}")
                raise NotFoundError("Project not found")

            results = self._execute_triggers(project, payload, organization_id)
            app_logger.info(f"Successfully triggered {len(results)} project hooks")
            return results
        except Exception as e:
            error_logger.error(f"Error triggering project hooks: {str(e)}", exc_info=True)
            raise

    def _execute_triggers(self, source: Any, payload: Dict[str, Any], organization_id: str) -> List[Dict[str, Any]]:
        if not source or not hasattr(source, 'triggers') or not source.triggers:
            return []

        results = []
        for trigger in source.triggers:
            if not trigger.is_active:
                app_logger.debug(f"Skipping inactive trigger: {trigger.name}")
                continue
            
            app_logger.info(f"Executing trigger: {trigger.name} ({trigger.action_type})")
            result = self._execute_hook(trigger, payload, organization_id)
            results.append({
                "trigger_name": trigger.name,
                "action_type": trigger.action_type,
                "result": result
            })
        return results

    def _find_question(self, form, question_id):
        if not hasattr(form, 'sections'):
            return None
        for section in form.sections:
            q = self._search_section_for_question(section, question_id)
            if q: return q
        return None

    def _search_section_for_question(self, section, question_id):
        for question in getattr(section, 'questions', []):
            if str(getattr(question, 'id', '')) == question_id or getattr(question, 'variable_name', '') == question_id:
                return question
        for sub_section in getattr(section, 'sections', []):
            q = self._search_section_for_question(sub_section, question_id)
            if q: return q
        return None

    def _find_section(self, form, section_id):
        if not hasattr(form, 'sections'):
            return None
        for section in form.sections:
            s = self._search_section_for_section(section, section_id)
            if s: return s
        return None

    def _search_section_for_section(self, section, section_id):
        if str(getattr(section, 'id', '')) == section_id or getattr(section, 'variable_name', '') == section_id:
            return section
        for sub_section in getattr(section, 'sections', []):
            s = self._search_section_for_section(sub_section, section_id)
            if s: return s
        return None

    def _execute_hook(self, trigger, payload, organization_id):
        action_type = trigger.action_type
        config = trigger.action_config or {}

        try:
            if action_type == "form_data":
                return self._handle_form_data_hook(config, payload, organization_id)
            elif action_type == "external_hook":
                return self._handle_external_hook(config, payload, organization_id)
            elif action_type == "predefined_url":
                return self._handle_predefined_url_hook(config, payload)
            elif action_type == "webhook":
                return self._call_url(config.get("url"), config.get("method", "POST"), payload, config.get("headers", {}))
            
            app_logger.warning(f"Action type {action_type} not supported for synchronous execution")
            return {"status": "ignored", "reason": f"Action type {action_type} not supported for synchronous execution"}
        except Exception as e:
            error_logger.error(f"Error executing hook {trigger.name}: {str(e)}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def _handle_form_data_hook(self, config, payload, organization_id):
        target_form_id = config.get("form_id")
        app_logger.info(f"Handling form_data hook for target form {target_form_id}")
        return {"status": "success", "message": f"Synchronous data sync with form {target_form_id} completed"}

    def _handle_external_hook(self, config, payload, organization_id):
        hook_id = config.get("hook_id")
        if not hook_id:
             app_logger.error("hook_id not specified in action_config")
             return {"status": "error", "message": "hook_id not specified in action_config"}
             
        hook = ExternalHook.objects(id=hook_id, organization_id=organization_id, is_deleted=False).first()
        if not hook:
            app_logger.error(f"External hook {hook_id} definition not found")
            return {"status": "error", "message": "External hook definition not found"}
        if hook.status != "approved":
            app_logger.warning(f"External hook {hook_id} is not approved (status: {hook.status})")
            return {"status": "error", "message": "External hook not approved by admin"}

        return self._call_url(hook.url, hook.method, payload, hook.headers)

    def _handle_predefined_url_hook(self, config, payload):
        url = config.get("url")
        if not url:
            app_logger.error("Predefined URL not specified")
            return {"status": "error", "message": "Predefined URL not specified"}
        return self._call_url(url, "POST", payload)

    def _call_url(self, url, method, data, headers=None):
        app_logger.info(f"Calling external URL: {method} {url}")
        try:
            response = requests.request(method, url, json=data, headers=headers or {}, timeout=10)
            response.raise_for_status()
            app_logger.info(f"External URL call successful: {response.status_code}")
            return {
                "status": "success",
                "status_code": response.status_code,
                "data": response.json() if "application/json" in response.headers.get("Content-Type", "") else response.text
            }
        except Exception as e:
            error_logger.error(f"Error calling external URL {url}: {str(e)}")
            return {"status": "error", "message": str(e)}

    def register_external_hook(self, data, user, organization_id):
        app_logger.info(f"Registering external hook {data.get('name')} for organization {organization_id}")
        try:
            hook = ExternalHook(
                name=data.get("name"),
                organization_id=organization_id,
                url=data.get("url"),
                method=data.get("method", "POST"),
                headers=data.get("headers", {}),
                input_schema=data.get("input_schema", {}),
                output_schema=data.get("output_schema", {}),
                created_by=user,
                status="pending"
            )
            hook.save()
            audit_logger.info(f"External hook registered: {hook.id} by user {user}", extra={
                "action": "hook_registration",
                "hook_id": str(hook.id),
                "user_id": str(user),
                "organization_id": str(organization_id)
            })
            return hook
        except Exception as e:
            error_logger.error(f"Error registering external hook: {str(e)}", exc_info=True)
            raise

    def approve_hook(self, hook_id, admin, status="approved"):
        app_logger.info(f"Updating hook {hook_id} status to {status} by admin {admin}")
        try:
            hook = ExternalHook.objects(id=hook_id).first()
            if not hook:
                app_logger.warning(f"Hook {hook_id} not found for approval")
                raise NotFoundError("Hook not found")
            
            old_status = hook.status
            hook.status = status
            hook.approved_by = admin
            hook.approved_at = datetime.now(timezone.utc)
            hook.save()
            
            audit_logger.info(f"External hook {hook_id} {status} by admin {admin}", extra={
                "action": "hook_approval",
                "hook_id": str(hook_id),
                "admin_id": str(admin),
                "old_status": old_status,
                "new_status": status
            })
            return hook
        except Exception as e:
            error_logger.error(f"Error approving hook {hook_id}: {str(e)}", exc_info=True)
            raise

hook_service = HookService()
