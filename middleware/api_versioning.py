"""
middleware/api_versioning.py
API versioning middleware for handling multiple API versions.
"""

from flask import request, jsonify, g, current_app
import re
from functools import wraps
from logger.unified_logger import app_logger, error_logger

class APIVersionManager:
    """Manages API versioning and deprecation."""
    
    def __init__(self):
        self.supported_versions = ['v1', 'v2']
        self.default_version = 'v1'
        self.deprecated_versions = {}
        self.version_endpoints = {
            'v1': '/api/v1/',
            'v2': '/api/v2/'
        }
    
    def get_version_from_path(self, path):
        """Extract API version from request path."""
        # Match pattern like /api/v1/ or /api/v2/
        match = re.match(r'^/api/(v\d+)/', path)
        return match.group(1) if match else None
    
    def get_version_from_header(self, headers):
        """Extract API version from Accept header."""
        accept_header = headers.get('Accept', '')
        # Match pattern like application/vnd.mahasangraha.v1+json
        match = re.search(r'application/vnd\.mahasangraha\.(v\d+)\+json', accept_header)
        return match.group(1) if match else None
    
    def get_version_from_query(self, query_string):
        """Extract API version from query parameter."""
        return query_string.get('api_version')
    
    def determine_api_version(self):
        """Determine the API version from various sources."""
        # Priority: Header > Path > Query > Default
        version = None
        
        # Check Accept header first
        version = self.get_version_from_header(request.headers)
        
        # If not found, check path
        if not version:
            version = self.get_version_from_path(request.path)
        
        # If not found, check query parameter
        if not version:
            version = self.get_version_from_query(request.args)
        
        # If still not found, use default
        if not version:
            version = self.default_version
        
        # Validate version
        if version not in self.supported_versions:
            error_logger.warning(f"Unsupported API version requested: {version}")
            version = self.default_version
        
        return version
    
    def is_version_deprecated(self, version):
        """Check if a version is deprecated."""
        return version in self.deprecated_versions
    
    def get_deprecation_info(self, version):
        """Get deprecation information for a version."""
        return self.deprecated_versions.get(version, {})
    
    def set_deprecation(self, version, sunset_date, replacement_version=None):
        """Set deprecation information for a version."""
        self.deprecated_versions[version] = {
            'sunset_date': sunset_date,
            'replacement_version': replacement_version,
            'deprecated_at': datetime.utcnow()
        }
    
    def get_response_headers(self, version):
        """Get version-related response headers."""
        headers = {
            'X-API-Version': version
        }
        
        # Add deprecation headers if needed
        if self.is_version_deprecated(version):
            deprecation_info = self.get_deprecation_info(version)
            headers['Deprecation'] = 'true'
            headers['Sunset'] = deprecation_info['sunset_date']
            if deprecation_info.get('replacement_version'):
                headers['Link'] = f'<{self.version_endpoints[deprecation_info["replacement_version"]]}>; rel="successor-version"'
        
        return headers

# Global version manager instance
version_manager = APIVersionManager()

def api_version(min_version=None, max_version=None):
    """
    Decorator to specify API version requirements for a route.
    
    Args:
        min_version: Minimum version required (e.g., 'v1')
        max_version: Maximum version supported (e.g., 'v2')
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Determine API version
            version = version_manager.determine_api_version()
            
            # Store version in context
            g.api_version = version
            
            # Check version constraints
            if min_version and version < min_version:
                return jsonify({
                    "error": {
                        "code": "API_VERSION_TOO_LOW",
                        "message": f"API version {version} is not supported. Minimum version required: {min_version}",
                        "details": {
                            "current_version": version,
                            "min_version": min_version
                        }
                    }
                }), 400
            
            if max_version and version > max_version:
                return jsonify({
                    "error": {
                        "code": "API_VERSION_TOO_HIGH",
                        "message": f"API version {version} is not supported. Maximum version supported: {max_version}",
                        "details": {
                            "current_version": version,
                            "max_version": max_version
                        }
                    }
                }), 400
            
            # Call the original function
            response = f(*args, **kwargs)
            
            # Add version headers to response
            if hasattr(response, 'headers'):
                version_headers = version_manager.get_response_headers(version)
                for header, value in version_headers.items():
                    response.headers[header] = value
            
            return response
        return decorated_function
    return decorator

def require_api_version(version):
    """
    Decorator to require a specific API version.
    
    Args:
        version: Required version (e.g., 'v1')
    """
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Determine API version
            request_version = version_manager.determine_api_version()
            
            # Store version in context
            g.api_version = request_version
            
            # Check version
            if request_version != version:
                return jsonify({
                    "error": {
                        "code": "API_VERSION_MISMATCH",
                        "message": f"This endpoint requires API version {version}",
                        "details": {
                            "current_version": request_version,
                            "required_version": version
                        }
                    }
                }), 400
            
            # Call the original function
            response = f(*args, **kwargs)
            
            # Add version headers to response
            if hasattr(response, 'headers'):
                version_headers = version_manager.get_response_headers(request_version)
                for header, value in version_headers.items():
                    response.headers[header] = value
            
            return response
        return decorated_function
    return decorator

def add_version_headers(response):
    """Add API version headers to Flask response."""
    if hasattr(g, 'api_version'):
        version_headers = version_manager.get_response_headers(g.api_version)
        for header, value in version_headers.items():
            response.headers[header] = value
    return response

def get_version_info():
    """Get information about supported API versions."""
    return {
        "supported_versions": version_manager.supported_versions,
        "default_version": version_manager.default_version,
        "deprecated_versions": version_manager.deprecated_versions,
        "version_endpoints": version_manager.version_endpoints
    }

# Middleware to automatically add version headers
def add_version_headers(response):
    """Add API version headers to all responses."""
    if hasattr(g, 'api_version'):
        version_headers = version_manager.get_response_headers(g.api_version)
        for header, value in version_headers.items():
            response.headers[header] = value
    return response