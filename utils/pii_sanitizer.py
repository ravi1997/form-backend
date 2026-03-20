"""
utils/pii_sanitizer.py
PII (Personally Identifiable Information) Redaction for AI prompts.
Ensures sensitive data doesn't leak to external inference providers.
"""
import re

PII_PATTERNS = {
    "email": r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
    "phone": r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
    "ssn": r"\d{3}-\d{2}-\d{4}",
    "credit_card": r"\b(?:\d[ -]*?){13,16}\b",
    "ipv4": r"\b(?:\d{1,3}\.){3}\d{1,3}\b"
}

def sanitize_text(text: str, mask: str = "[REDACTED]") -> str:
    """Redacts PII patterns from the given text."""
    if not text:
        return text
    
    sanitized = text
    for name, pattern in PII_PATTERNS.items():
        sanitized = re.sub(pattern, f"{mask}_{name.upper()}", sanitized)
    
    return sanitized

def sanitize_dict(data: dict) -> dict:
    """Recursively redacts PII from dictionary values."""
    sanitized = {}
    for k, v in data.items():
        if isinstance(v, str):
            sanitized[k] = sanitize_text(v)
        elif isinstance(v, dict):
            sanitized[k] = sanitize_dict(v)
        elif isinstance(v, list):
            sanitized[k] = [sanitize_text(item) if isinstance(item, str) else item for item in v]
        else:
            sanitized[k] = v
    return sanitized
