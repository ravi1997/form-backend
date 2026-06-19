"""
services/llm_prompt_template_service.py
Service for managing LLM prompt templates with variables and versioning.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
from enum import Enum
import re
import uuid
import json

from logger.unified_logger import app_logger, error_logger
from models.llm_model import LLMPromptTemplate
from utils.exceptions import ValidationError, NotFoundError


class TemplateCategory(Enum):
    """Template categories."""
    FORM_GENERATION = "form_generation"
    RESPONSE_ANALYSIS = "response_analysis"
    DASHBOARD_QUERY = "dashboard_query"
    FORM_SUGGESTIONS = "form_suggestions"
    DATA_SUMMARIZATION = "data_summarization"
    CUSTOM = "custom"


class LLMPromptTemplateService:
    """Service for managing LLM prompt templates."""

    def __init__(self):
        self._templates_cache = {}  # Cache for active templates
        self._last_cache_update = None

    async def create_template(
        self,
        name: str,
        template_text: str,
        category: str,
        description: str = "",
        variables: List[Dict[str, Any]] = None,
        provider: str = None,
        model_id: str = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        tags: List[str] = None,
        organization_id: str = None,
        created_by: str = None,
        is_public: bool = False
    ) -> LLMPromptTemplate:
        """Create a new prompt template."""
        try:
            app_logger.info(f"Creating prompt template: {name}")
            
            # Validate template
            self._validate_template(template_text, variables or [])
            
            # Check if template with same name already exists
            existing_template = LLMPromptTemplate.objects(
                name=name,
                organization_id=organization_id,
                is_deleted=False
            ).first()
            
            if existing_template:
                raise ValidationError(f"Template with name '{name}' already exists")
            
            # Create template
            template = LLMPromptTemplate(
                name=name,
                template_text=template_text,
                category=category,
                description=description,
                variables=variables or [],
                provider=provider,
                model_id=model_id,
                temperature=temperature,
                max_tokens=max_tokens,
                tags=tags or [],
                organization_id=organization_id,
                created_by=created_by,
                is_public=is_public
            )
            template.save()
            
            # Clear cache
            self._clear_cache()
            
            app_logger.info(f"Successfully created prompt template: {template.id}")
            return template
            
        except Exception as e:
            error_logger.error(f"Failed to create prompt template: {str(e)}", exc_info=True)
            raise

    async def get_template(self, template_id: str) -> Dict[str, Any]:
        """Get a template by ID."""
        try:
            # Check cache first
            if self._is_cache_valid() and template_id in self._templates_cache:
                return self._templates_cache[template_id]
            
            # Get template
            template = LLMPromptTemplate.objects(
                id=template_id,
                is_deleted=False
            ).first()
            
            if not template:
                raise NotFoundError(f"Template not found: {template_id}")
            
            # Build response
            result = {
                "id": str(template.id),
                "name": template.name,
                "template_text": template.template_text,
                "category": template.category,
                "description": template.description,
                "variables": template.variables,
                "provider": template.provider,
                "model_id": template.model_id,
                "temperature": template.temperature,
                "max_tokens": template.max_tokens,
                "tags": template.tags,
                "organization_id": str(template.organization_id) if template.organization_id else None,
                "created_by": template.created_by,
                "is_public": template.is_public,
                "usage_count": template.usage_count,
                "created_at": template.created_at.isoformat(),
                "updated_at": template.updated_at.isoformat()
            }
            
            # Cache result
            if self._is_cache_valid():
                self._templates_cache[template_id] = result
            
            return result
            
        except Exception as e:
            error_logger.error(f"Failed to get template: {str(e)}", exc_info=True)
            raise

    async def update_template(
        self,
        template_id: str,
        name: str = None,
        template_text: str = None,
        category: str = None,
        description: str = None,
        variables: List[Dict[str, Any]] = None,
        provider: str = None,
        model_id: str = None,
        temperature: float = None,
        max_tokens: int = None,
        tags: List[str] = None,
        updated_by: str = None
    ) -> Dict[str, Any]:
        """Update a template."""
        try:
            app_logger.info(f"Updating template: {template_id}")
            
            # Get template
            template = LLMPromptTemplate.objects(
                id=template_id,
                is_deleted=False
            ).first()
            
            if not template:
                raise NotFoundError(f"Template not found: {template_id}")
            
            # Update fields
            if name is not None:
                template.name = name
            
            if template_text is not None:
                self._validate_template(template_text, variables or template.variables)
                template.template_text = template_text
            
            if category is not None:
                template.category = category
            
            if description is not None:
                template.description = description
            
            if variables is not None:
                self._validate_template(template.template_text, variables)
                template.variables = variables
            
            if provider is not None:
                template.provider = provider
            
            if model_id is not None:
                template.model_id = model_id
            
            if temperature is not None:
                template.temperature = temperature
            
            if max_tokens is not None:
                template.max_tokens = max_tokens
            
            if tags is not None:
                template.tags = tags
            
            template.updated_by = updated_by
            template.updated_at = datetime.utcnow()
            template.save()
            
            # Clear cache
            self._clear_cache()
            
            app_logger.info(f"Successfully updated template: {template_id}")
            return await self.get_template(template_id)
            
        except Exception as e:
            error_logger.error(f"Failed to update template: {str(e)}", exc_info=True)
            raise

    async def delete_template(self, template_id: str, deleted_by: str = None) -> bool:
        """Delete a template (soft delete)."""
        try:
            app_logger.info(f"Deleting template: {template_id}")
            
            # Get template
            template = LLMPromptTemplate.objects(
                id=template_id,
                is_deleted=False
            ).first()
            
            if not template:
                raise NotFoundError(f"Template not found: {template_id}")
            
            # Soft delete
            template.is_deleted = True
            template.deleted_by = deleted_by
            template.deleted_at = datetime.utcnow()
            template.save()
            
            # Clear cache
            self._clear_cache()
            
            app_logger.info(f"Successfully deleted template: {template_id}")
            return True
            
        except Exception as e:
            error_logger.error(f"Failed to delete template: {str(e)}", exc_info=True)
            raise

    async def list_templates(
        self,
        category: str = None,
        provider: str = None,
        organization_id: str = None,
        is_public: bool = None,
        tags: List[str] = None,
        search: str = None,
        page: int = 1,
        page_size: int = 50
    ) -> Dict[str, Any]:
        """List templates with filtering and pagination."""
        try:
            query = LLMPromptTemplate.objects(is_deleted=False)
            
            if category:
                query = query.filter(category=category)
            
            if provider:
                query = query.filter(provider=provider)
            
            if organization_id:
                # Include templates from the organization and public templates
                query = query.filter(
                    __raw__={
                        "$or": [
                            {"organization_id": organization_id},
                            {"is_public": True}
                        ]
                    }
                )
            elif is_public is not None:
                query = query.filter(is_public=is_public)
            
            if tags:
                query = query.filter(tags__all=tags)
            
            if search:
                # Search in name, description, and template text
                search_regex = re.compile(search, re.IGNORECASE)
                query = query.filter(
                    __raw__={
                        "$or": [
                            {"name": search_regex},
                            {"description": search_regex},
                            {"template_text": search_regex}
                        ]
                    }
                )
            
            # Get total count
            total_count = query.count()
            
            # Apply pagination
            skip = (page - 1) * page_size
            templates = query.skip(skip).limit(page_size).order_by("-created_at")
            
            # Build response
            template_list = []
            for template in templates:
                template_data = {
                    "id": str(template.id),
                    "name": template.name,
                    "category": template.category,
                    "description": template.description,
                    "provider": template.provider,
                    "model_id": template.model_id,
                    "temperature": template.temperature,
                    "max_tokens": template.max_tokens,
                    "tags": template.tags,
                    "organization_id": str(template.organization_id) if template.organization_id else None,
                    "is_public": template.is_public,
                    "usage_count": template.usage_count,
                    "created_at": template.created_at.isoformat(),
                    "updated_at": template.updated_at.isoformat()
                }
                
                template_list.append(template_data)
            
            return {
                "templates": template_list,
                "total_count": total_count,
                "page": page,
                "page_size": page_size,
                "total_pages": (total_count + page_size - 1) // page_size
            }
            
        except Exception as e:
            error_logger.error(f"Failed to list templates: {str(e)}", exc_info=True)
            raise

    async def apply_template(
        self,
        template: Dict[str, Any],
        prompt: str,
        variables: Dict[str, Any] = None
    ) -> str:
        """Apply a template with variables to a prompt."""
        try:
            template_text = template["template_text"]
            template_vars = template.get("variables", [])
            
            # Create context dictionary
            context = {
                "prompt": prompt,
                **(variables or {})
            }
            
            # Apply template variables
            result = template_text
            
            # Replace {{variable}} placeholders
            for var in template_vars:
                var_name = var["name"]
                var_default = var.get("default", "")
                
                # Try to get value from context, use default if not found
                value = str(context.get(var_name, var_default))
                
                # Replace placeholder
                placeholder = f"{{{{{var_name}}}}}"
                result = result.replace(placeholder, value)
            
            # Replace any remaining placeholders with empty strings
            result = re.sub(r'\{\{[^}]+\}\}', '', result)
            
            # Clean up multiple newlines
            result = re.sub(r'\n\s*\n\s*\n', '\n\n', result)
            
            return result.strip()
            
        except Exception as e:
            error_logger.error(f"Failed to apply template: {str(e)}", exc_info=True)
            raise

    async def record_template_usage(self, template_id: str):
        """Record that a template was used."""
        try:
            template = LLMPromptTemplate.objects(
                id=template_id,
                is_deleted=False
            ).first()
            
            if template:
                template.usage_count = (template.usage_count or 0) + 1
                template.last_used_at = datetime.utcnow()
                template.save()
            
        except Exception as e:
            error_logger.error(f"Failed to record template usage: {str(e)}", exc_info=True)
            # Don't raise here as this is not critical

    async def create_system_templates(self):
        """Create system-defined templates."""
        try:
            app_logger.info("Creating system prompt templates")
            
            system_templates = [
                {
                    "name": "Form Generation",
                    "template_text": """You are an expert form builder. Based on the following description, create a JSON form structure with appropriate fields.

Description: {{prompt}}

Current form structure (if any):
{{current_form}}

Generate a JSON form structure with the following format:
{
  "title": "Form Title",
  "description": "Form Description",
  "sections": [
    {
      "title": "Section Title",
      "fields": [
        {
          "type": "text_input|dropdown|checkbox|etc",
          "label": "Field Label",
          "required": true/false,
          "placeholder": "Placeholder text",
          "options": ["Option 1", "Option 2"] // for dropdown/radio
        }
      ]
    }
  ]
}

Return only the JSON structure, no explanations.""",
                    "category": TemplateCategory.FORM_GENERATION.value,
                    "description": "Generate form structure from natural language description",
                    "variables": [
                        {"name": "prompt", "description": "Natural language description of the form", "required": True},
                        {"name": "current_form", "description": "Current form structure (JSON)", "required": False, "default": "{}"}
                    ],
                    "provider": "openai",
                    "model_id": "gpt-4",
                    "temperature": 0.3,
                    "max_tokens": 2000,
                    "tags": ["form", "generation", "ai"],
                    "is_public": True
                },
                {
                    "name": "Response Analysis",
                    "template_text": """You are an expert data analyst. Analyze the following form responses and provide insights.

Responses data:
{{responses}}

Analysis request: {{prompt}}

Provide a comprehensive analysis including:
1. Key patterns and trends
2. Notable insights or anomalies
3. Statistical summary
4. Recommendations based on the data

Format your response as a structured JSON object:
{
  "summary": "Brief summary of findings",
  "key_insights": ["Insight 1", "Insight 2"],
  "patterns": ["Pattern 1", "Pattern 2"],
  "statistics": {
    "total_responses": number,
    "key_metrics": {...}
  },
  "recommendations": ["Recommendation 1", "Recommendation 2"]
}""",
                    "category": TemplateCategory.RESPONSE_ANALYSIS.value,
                    "description": "Analyze form responses and provide insights",
                    "variables": [
                        {"name": "responses", "description": "Form responses data (JSON)", "required": True},
                        {"name": "prompt", "description": "Analysis request or question", "required": True}
                    ],
                    "provider": "openai",
                    "model_id": "gpt-4",
                    "temperature": 0.5,
                    "max_tokens": 1500,
                    "tags": ["analysis", "responses", "insights"],
                    "is_public": True
                },
                {
                    "name": "Dashboard Query",
                    "template_text": """You are a dashboard query expert. Convert the following natural language query into structured filters for a dashboard.

Natural language query: {{prompt}}

Dashboard context: {{dashboard_context}}

Convert the query into JSON filter structure:
{
  "filters": [
    {
      "field": "field_name",
      "operator": "equals|contains|greater_than|less_than",
      "value": "filter_value"
    }
  ],
  "sort": [
    {
      "field": "field_name",
      "direction": "asc|desc"
    }
  ],
  "limit": number
}

Return only the JSON structure, no explanations.""",
                    "category": TemplateCategory.DASHBOARD_QUERY.value,
                    "description": "Convert natural language to dashboard filters",
                    "variables": [
                        {"name": "prompt", "description": "Natural language query", "required": True},
                        {"name": "dashboard_context", "description": "Dashboard context and available fields", "required": True}
                    ],
                    "provider": "openai",
                    "model_id": "gpt-4",
                    "temperature": 0.2,
                    "max_tokens": 1000,
                    "tags": ["dashboard", "query", "filters"],
                    "is_public": True
                },
                {
                    "name": "Form Suggestions",
                    "template_text": """You are a form design expert. Review the following form structure and provide suggestions for improvement.

Form structure:
{{current_form}}

Analyze the form and provide suggestions in the following JSON format:
{
  "overall_assessment": "Brief assessment of the form",
  "suggestions": [
    {
      "type": "field|section|layout|logic",
      "target": "field_id or section_id",
      "description": "Description of the suggestion",
      "priority": "high|medium|low",
      "reasoning": "Why this suggestion would improve the form"
    }
  ],
  "best_practices": ["Best practice 1", "Best practice 2"]
}""",
                    "category": TemplateCategory.FORM_SUGGESTIONS.value,
                    "description": "Get AI suggestions for form improvements",
                    "variables": [
                        {"name": "current_form", "description": "Current form structure (JSON)", "required": True}
                    ],
                    "provider": "openai",
                    "model_id": "gpt-4",
                    "temperature": 0.6,
                    "max_tokens": 1500,
                    "tags": ["form", "suggestions", "improvement"],
                    "is_public": True
                }
            ]
            
            created_templates = []
            for template_data in system_templates:
                try:
                    template = await self.create_template(**template_data)
                    created_templates.append(template)
                except Exception as e:
                    error_logger.warning(f"Failed to create system template {template_data['name']}: {str(e)}")
            
            app_logger.info(f"Successfully created {len(created_templates)} system templates")
            return created_templates
            
        except Exception as e:
            error_logger.error(f"Failed to create system templates: {str(e)}", exc_info=True)
            raise

    def _validate_template(self, template_text: str, variables: List[Dict[str, Any]]):
        """Validate template text and variables."""
        if not template_text or not template_text.strip():
            raise ValidationError("Template text cannot be empty")
        
        # Check for required variables
        required_vars = set()
        optional_vars = set()
        
        # Find all variable placeholders in template
        placeholders = re.findall(r'\{\{([^}]+)\}\}', template_text)
        for placeholder in placeholders:
            var_name = placeholder.strip()
            required_vars.add(var_name)
        
        # Check if all required variables are defined
        for var in variables:
            var_name = var["name"]
            if var_name in required_vars:
                required_vars.remove(var_name)
            optional_vars.add(var_name)
        
        # If there are still required variables not defined, raise error
        if required_vars:
            raise ValidationError(f"Required variables not defined: {', '.join(required_vars)}")

    def _clear_cache(self):
        """Clear the templates cache."""
        self._templates_cache = {}
        self._last_cache_update = None

    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid."""
        if not self._last_cache_update:
            return False
        
        # Cache expires after 5 minutes
        cache_duration = 300  # seconds
        return (datetime.utcnow() - self._last_cache_update).total_seconds() < cache_duration

    async def warm_cache(self):
        """Warm up the cache with frequently used templates."""
        try:
            app_logger.info("Warming up prompt templates cache")
            
            # Get public templates and most used templates
            templates = LLMPromptTemplate.objects(
                is_deleted=False,
                is_public=True
            ).limit(50)
            
            for template in templates:
                try:
                    await self.get_template(str(template.id))
                except Exception as e:
                    error_logger.warning(f"Failed to cache template {template.id}: {str(e)}")
            
            self._last_cache_update = datetime.utcnow()
            app_logger.info("Successfully warmed up prompt templates cache")
            
        except Exception as e:
            error_logger.error(f"Failed to warm up cache: {str(e)}", exc_info=True)