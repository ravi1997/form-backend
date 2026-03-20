"""
utils/schema_generator.py
Generates dynamic Pydantic models from FormVersion definitions for high-performance validation.
Includes thread-safe caching.
"""
from typing import Dict, Any, Type, Optional
from pydantic import create_model, Field, validator
import threading

# Global cache for compiled models
_MODEL_CACHE: Dict[str, Type] = {}
_CACHE_LOCK = threading.Lock()

def _get_pydantic_type(field_type: str) -> Type:
    """Maps form field types to Pydantic/Python types."""
    mapping = {
        "input": str,
        "textarea": str,
        "number": float,
        "email": str, # Could use Pydantic EmailStr if available
        "mobile": str,
        "url": str,
        "password": str,
        "date": str,
        "boolean": bool
    }
    return mapping.get(field_type, Any)

def generate_form_model(version_id: str, sections: list) -> Type:
    """
    Generates a Pydantic model from a list of sections/questions.
    Caches the result for performance.
    """
    with _CACHE_LOCK:
        if version_id in _MODEL_CACHE:
            return _MODEL_CACHE[version_id]

    fields = {}
    
    def process_sections(sec_list):
        for section in sec_list:
            for question in section.questions:
                var_name = question.variable_name
                if not var_name:
                    continue
                    
                p_type = _get_pydantic_type(question.field_type)
                
                # Validation rules
                v = question.validation
                kwargs = {
                    "description": question.help_text,
                    "default": question.default_value if not v.is_required else ...
                }
                
                if v.min_length is not None: kwargs["min_length"] = v.min_length
                if v.max_length is not None: kwargs["max_length"] = v.max_length
                if v.regex: kwargs["pattern"] = v.regex
                
                fields[var_name] = (p_type, Field(**kwargs))
            
            if section.sections:
                process_sections(section.sections)

    process_sections(sections)
    
    # Create the dynamic model
    model = create_model(f"FormModel_{version_id.replace('-', '_')}", **fields)
    
    with _CACHE_LOCK:
        _MODEL_CACHE[version_id] = model
        
    return model
