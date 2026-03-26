"""
utils/schema_generator.py
Generates dynamic Pydantic models from FormVersion definitions for high-performance validation.
Includes thread-safe caching.
"""
from typing import Dict, Any, Type, Optional, List, Union, Annotated
from pydantic import create_model, Field, AfterValidator, BeforeValidator
import threading
import re
from datetime import datetime, date

# Global cache for compiled models
_MODEL_CACHE: Dict[str, Type] = {}
_CACHE_LOCK = threading.Lock()

def _get_pydantic_type(field_type: str, is_repeatable: bool = False) -> Type:
    """Maps form field types to Pydantic/Python types."""
    if field_type == "matrix_choice":
        return Optional[Dict[str, str]]
        
    mapping = {
        "input": str,
        "textarea": str,
        "number": float,
        "price": float,
        "age": float,
        "slider": float,
        "range": float,
        "rating": float,
        "stepper": float,
        "email": str,
        "mobile": str,
        "url": str,
        "password": str,
        "date": str,
        "datetime": str,
        "datetime-local": str,
        "month": str,
        "week": str,
        "date_range": str,
        "boolean": bool,
        "checkbox": bool,
        "select": str,
        "dropdown": str,
        "radio": str,
        "multi_select": List[Any],
        "checkboxes": List[Any],
        "multi_checkbox": List[Any],
        "email_list": List[str],
    }
    base_type = mapping.get(field_type, Any)
    if is_repeatable:
        return List[base_type]
    return base_type

def date_validator(v: Any, validation: Any) -> Any:
    if v in (None, ""):
        return v
    
    try:
        if isinstance(v, (datetime, date)):
            dt = v
        else:
            # Try parsing common formats
            try:
                dt = datetime.fromisoformat(str(v))
            except ValueError:
                dt = datetime.strptime(str(v), "%Y-%m-%d")
        
        submitted_date = dt.date() if isinstance(dt, datetime) else dt
        today = date.today()

        if validation.disable_past_dates and submitted_date < today:
            raise ValueError("Date cannot be in the past")
        if validation.disable_future_dates and submitted_date > today:
            raise ValueError("Date cannot be in the future")
        if validation.disable_weekends and submitted_date.weekday() >= 5:
            raise ValueError("Weekends are not allowed")
        
        if validation.date_min:
            min_dt = datetime.fromisoformat(validation.date_min).date()
            if submitted_date < min_dt:
                raise ValueError(f"Date must be on or after {validation.date_min}")
        
        if validation.date_max:
            max_dt = datetime.fromisoformat(validation.date_max).date()
            if submitted_date > max_dt:
                raise ValueError(f"Date must be on or before {validation.date_max}")
                
    except (ValueError, TypeError) as e:
        if isinstance(e, ValueError) and str(e) in [
            "Date cannot be in the past", "Date cannot be in the future", 
            "Weekends are not allowed", f"Date must be on or after {validation.date_min}",
            f"Date must be on or before {validation.date_max}"
        ]:
            raise e
        # If parsing fails, we skip validation or let Pydantic handle it
        pass
    return v

def word_count_validator(v: Any, validation: Any) -> Any:
    if not isinstance(v, str) or not v:
        return v
    
    word_count = len(v.split())
    if validation.min_word_count is not None and word_count < validation.min_word_count:
        raise ValueError(f"Minimum word count is {validation.min_word_count}")
    if validation.max_word_count is not None and word_count > validation.max_word_count:
        raise ValueError(f"Maximum word count is {validation.max_word_count}")
    return v

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
                    
                p_type = _get_pydantic_type(question.field_type, question.is_repeatable)
                
                # Validation rules
                v = question.validation
                kwargs = {
                    "description": question.help_text,
                    "default": question.default_value if not v.is_required else ...
                }
                
                # 3a. Numeric min/max
                if question.field_type in ["number", "price", "age", "slider", "range", "rating", "stepper"]:
                    try:
                        if v.min_value is not None: kwargs["ge"] = float(v.min_value)
                        if v.max_value is not None: kwargs["le"] = float(v.max_value)
                    except (ValueError, TypeError):
                        pass

                # 3d. Selection count
                if question.field_type in ["multi_select", "checkboxes", "multi_checkbox", "email_list"]:
                    if v.min_selection is not None: kwargs["min_length"] = v.min_selection
                    if v.max_selection is not None: kwargs["max_length"] = v.max_selection

                # Basic validation
                if v.min_length is not None: kwargs["min_length"] = v.min_length
                if v.max_length is not None: kwargs["max_length"] = v.max_length
                if v.regex: kwargs["pattern"] = v.regex
                
                # 3b. Date validation & 3c. Word count via Annotated
                validators = []
                if question.field_type in ["date", "datetime", "datetime-local", "month", "week", "date_range"]:
                    validators.append(BeforeValidator(lambda val, v_obj=v: date_validator(val, v_obj)))
                
                if question.field_type in ["textarea", "paragraph", "rich_text", "textarea_editor", "markdown_editor", "short_text"]:
                    validators.append(AfterValidator(lambda val, v_obj=v: word_count_validator(val, v_obj)))

                if validators:
                    p_type = Annotated[p_type, *validators]

                fields[var_name] = (p_type, Field(**kwargs))

                # 3e. Requires confirmation
                if v.requires_confirmation:
                    confirm_var = f"{var_name}_confirm"
                    fields[confirm_var] = (p_type, Field(description=f"Confirm {question.label}", default=...))
            
            if section.sections:
                process_sections(section.sections)

    process_sections(sections)
    
    # Create the dynamic model
    model = create_model(f"FormModel_{version_id.replace('-', '_')}", **fields)
    
    with _CACHE_LOCK:
        _MODEL_CACHE[version_id] = model
        
    return model
