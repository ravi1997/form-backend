from typing import List, Dict, Any, Optional
from models.Form import Section, Form
from services.base import BaseService
from schemas.form import SectionSchema
from utils.exceptions import NotFoundError, ValidationError
from logger.unified_logger import app_logger

class SectionService(BaseService):
    def __init__(self):
        super().__init__(model=Section, schema=SectionSchema)

    @staticmethod
    def _normalize_option(option: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(option or {})
        # Backward compatibility for common API payloads.
        if "option_label" not in normalized and "label" in normalized:
            normalized["option_label"] = normalized.pop("label")
        if "option_value" not in normalized and "value" in normalized:
            normalized["option_value"] = normalized.pop("value")
        return normalized

    @staticmethod
    def _normalize_question(question: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(question or {})

        # Common alias support.
        if normalized.get("field_type") == "text":
            normalized["field_type"] = "input"

        # Support legacy/current clients sending top-level required boolean.
        if "required" in normalized:
            required = bool(normalized.pop("required"))
            validation = dict(normalized.get("validation") or {})
            validation["is_required"] = required
            normalized["validation"] = validation

        if isinstance(normalized.get("options"), list):
            normalized["options"] = [
                SectionService._normalize_option(opt) for opt in normalized["options"]
            ]

        return normalized

    @staticmethod
    def _normalize_section_payload(section_data: Dict[str, Any]) -> Dict[str, Any]:
        normalized = dict(section_data or {})

        # Allow callers to send repeat controls at section top-level.
        if any(k in normalized for k in ("is_repeatable", "repeat_min", "repeat_max")):
            logic = dict(normalized.get("logic") or {})
            if "is_repeatable" in normalized:
                logic["is_repeatable"] = bool(normalized.pop("is_repeatable"))
            if "repeat_min" in normalized:
                logic["repeat_min"] = normalized.pop("repeat_min")
            if "repeat_max" in normalized:
                logic["repeat_max"] = normalized.pop("repeat_max")
            normalized["logic"] = logic

        if isinstance(normalized.get("questions"), list):
            normalized["questions"] = [
                SectionService._normalize_question(q) for q in normalized["questions"]
            ]

        if isinstance(normalized.get("sections"), list):
            normalized["sections"] = [
                SectionService._normalize_section_payload(s)
                for s in normalized["sections"]
            ]

        return normalized

    def create_section(self, form_id: str, section_data: Dict[str, Any], organization_id: str) -> Section:
        """Creates a new section and appends it to the form."""
        form = Form.objects(id=form_id, organization_id=organization_id, is_deleted=False).first()
        if not form:
            raise NotFoundError("Form not found")
            
        # Create section
        normalized_data = self._normalize_section_payload(section_data)
        section = Section(**normalized_data)
        section.organization_id = organization_id
        section.save()
        
        # Add to form
        form.sections.append(section)
        form.save()

        # Keep draft version metadata in sync with the current section tree.
        from services.form_service import FormService
        form_version = FormService().sync_draft_version(form_id, organization_id)
        if form_version and form_version.version:
            section.version = form_version.version
            section.save()
        
        return section

    def delete_section(self, form_id: str, section_id: str, organization_id: str):
        """Removes a section from a form and soft-deletes it."""
        form = Form.objects(id=form_id, organization_id=organization_id, is_deleted=False).first()
        if not form:
            raise NotFoundError("Form not found")
            
        section = Section.objects(id=section_id, organization_id=organization_id, is_deleted=False).first()
        if not section:
            raise NotFoundError("Section not found")
            
        # Remove reference from form
        if section in form.sections:
            form.sections.remove(section)
            form.save()
            
        # Soft delete the section
        section.soft_delete()
        
    def update_section_order(self, form_id: str, section_ids: List[str], organization_id: str):
        """Updates the order of sections in a form."""
        form = Form.objects(id=form_id, organization_id=organization_id, is_deleted=False).first()
        if not form:
            raise NotFoundError("Form not found")
            
        # Reorder based on provided IDs
        new_sections = []
        for sid in section_ids:
            s = next((sec for sec in form.sections if str(sec.id) == sid), None)
            if s:
                new_sections.append(s)
                
        form.sections = new_sections
        form.save()
