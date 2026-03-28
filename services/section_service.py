from typing import List, Dict, Any, Optional
from models.Form import Section, Form
from services.base import BaseService
from schemas.form import SectionSchema
from utils.exceptions import NotFoundError, ValidationError
from logger.unified_logger import app_logger

class SectionService(BaseService):
    def __init__(self):
        super().__init__(model=Section, schema=SectionSchema)

    def create_section(self, form_id: str, section_data: Dict[str, Any], organization_id: str) -> Section:
        """Creates a new section and appends it to the form."""
        form = Form.objects(id=form_id, organization_id=organization_id, is_deleted=False).first()
        if not form:
            raise NotFoundError("Form not found")
            
        # Create section
        section = Section(**section_data)
        section.organization_id = organization_id
        section.save()
        
        # Add to form
        form.sections.append(section)
        form.save()
        
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
