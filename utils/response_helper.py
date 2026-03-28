from flask import jsonify
from datetime import datetime

class BaseSerializer:
    @staticmethod
    def clean_dict(data):
        """Recursively removes internal mongo fields and stringifies UUIDs/Dates."""
        if isinstance(data, list):
            return [BaseSerializer.clean_dict(i) for i in data]
        if not isinstance(data, dict):
            return data

        cleaned = {}
        # HARDENED: Expanded list of internal/sensitive fields to exclude
        EXCLUDE_FIELDS = (
            "_id", "_cls", "organization_id", "__v", 
            "editors", "viewers", "submitters", # ACL internals
            "snapshot_ref", "snapshot", # Snapshot raw data (use resolved fields)
            "meta_data", "internal_metadata", # Internal flags
            "password_hash", "salt" # Security
        )
        
        for k, v in data.items():
            if k in EXCLUDE_FIELDS:
                continue
            
            # Key mapping
            if k == "id" or k == "_id":
                cleaned["id"] = str(v)
            elif isinstance(v, datetime):
                cleaned[k] = v.isoformat()
            elif isinstance(v, dict):
                cleaned[k] = BaseSerializer.clean_dict(v)
            elif isinstance(v, list):
                cleaned[k] = [BaseSerializer.clean_dict(i) for i in v]
            else:
                cleaned[k] = v
        return cleaned

class FormSerializer(BaseSerializer):
    @staticmethod
    def serialize(form_dict, include_snapshot=False):
        """Sanitizes form dictionary for public API output."""
        cleaned = BaseSerializer.clean_dict(form_dict)
        
        # Ensure versions are cleaned but don't leak full snapshot unless requested
        if "versions" in cleaned:
            for v in cleaned["versions"]:
                if not include_snapshot:
                    v.pop("snapshot", None)
                    v.pop("snapshot_data", None)
                elif "snapshot" in v:
                    v["snapshot"] = BaseSerializer.clean_dict(v["snapshot"])
        
        # Clean top-level snapshots if any leaked through
        cleaned.pop("snapshot", None)
        cleaned.pop("snapshot_data", None)
        
        return cleaned

def success_response(data=None, message="Success", status_code=200):
    """
    Standard successful response envelope.
    """
    response = {
        "success": True,
        "message": message
    }
    if data is not None:
        response["data"] = data
        
    return jsonify(response), status_code

def error_response(message="An error occurred", details=None, status_code=400):
    """
    Standard error response envelope.
    """
    response = {
        "success": False,
        "error": message
    }
    if details is not None:
        response["details"] = details
        
    return jsonify(response), status_code

def get_pagination_params():
    """
    Extracts pagination parameters from request query arguments.
    Enforces safe defaults and max limits defined in settings.
    """
    from flask import request
    from config.settings import settings
    
    try:
        page = int(request.args.get("page", 1))
        page_size = int(request.args.get("page_size", settings.DEFAULT_PAGE_SIZE))
    except (ValueError, TypeError):
        page = 1
        page_size = settings.DEFAULT_PAGE_SIZE

    # Enforce safe bounds
    page = max(1, page)
    page_size = max(1, min(page_size, settings.MAX_PAGE_SIZE))
    
    return page, page_size
