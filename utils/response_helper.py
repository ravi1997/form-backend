from flask import jsonify

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
