"""
middleware/compliance_enforcement.py
Compliance enforcement middleware for GDPR, HIPAA, and other regulatory standards.
"""

from flask import request, g, jsonify
from functools import wraps
from datetime import datetime, timezone
from logger.unified_logger import app_logger, error_logger, audit_logger
from services.audit_service import AuditService
from services.compliance_service import ComplianceService
from services.gdpr_compliance_service import gdpr_compliance_service
from utils.response_helper import error_response


class ComplianceEnforcementMiddleware:
    """Middleware for enforcing compliance requirements based on organization settings."""
    
    def __init__(self):
        self.audit_service = AuditService()
        self.compliance_service = ComplianceService()
        self.gdpr_service = gdpr_compliance_service
    
    def enforce_compliance(self, f):
        """
        Decorator to enforce compliance requirements for API endpoints.
        """
        @wraps(f)
        def decorated_function(*args, **kwargs):
            # Get organization from context
            org_id = getattr(g, 'org_id', None)
            if not org_id:
                # Try to get org_id from user
                user = getattr(g, 'current_user', None)
                if user and hasattr(user, 'org_id'):
                    org_id = user.org_id
            
            if not org_id:
                # No organization context, skip compliance enforcement
                return f(*args, **kwargs)
            
            # Check organization's compliance requirements
            try:
                compliance_standards = self.compliance_service.get_org_compliance_standards(org_id)
                
                # Enforce GDPR requirements
                if 'GDPR' in compliance_standards:
                    self._enforce_gdpr_requirements(org_id)
                
                # Enforce HIPAA requirements
                if 'HIPAA' in compliance_standards:
                    self._enforce_hipaa_requirements(org_id)
                
                # Log compliance check
                self.audit_service.append_event(
                    tenant_id=org_id,
                    actor_id=getattr(g, 'current_user_id', 'system'),
                    action='compliance_check',
                    resource=f'endpoint:{request.endpoint}',
                    metadata={
                        'compliance_standards': list(compliance_standards),
                        'method': request.method,
                        'path': request.path
                    }
                )
                
            except Exception as e:
                error_logger.error(f"Error in compliance enforcement: {e}")
                # Continue with request but log the error
            
            return f(*args, **kwargs)
        return decorated_function
    
    def _enforce_gdpr_requirements(self, org_id):
        """Enforce GDPR compliance requirements."""
        # Anonymize IP address in logs
        if hasattr(request, 'remote_addr'):
            ip_address = request.remote_addr
            if ip_address:
                # Anonymize the last octet for IPv4
                if '.' in ip_address:
                    parts = ip_address.split('.')
                    if len(parts) == 4:
                        anonymized_ip = f"{parts[0]}.{parts[1]}.{parts[2]}.0"
                        g.anonymized_ip = anonymized_ip
                # Anonymize IPv6 (simplified)
                elif ':' in ip_address:
                    g.anonymized_ip = ip_address.split(':')[0] + '::'
        
        # Check for consent requirements
        if self.gdpr_service.requires_consent_check(org_id, request.endpoint):
            # For form submissions, check if consent is given
            if request.is_json and request.get_json():
                data = request.get_json()
                if not data.get('gdpr_consent', False):
                    # Check if this is a form submission endpoint
                    if 'form' in request.endpoint or 'response' in request.endpoint:
                        return error_response(
                            "GDPR consent is required",
                            status_code=400,
                            error_code="GDPR_CONSENT_REQUIRED"
                        )
    
    def _enforce_hipaa_requirements(self, org_id):
        """Enforce HIPAA compliance requirements."""
        # Log all data access events
        if hasattr(g, 'current_user_id'):
            self.audit_service.append_event(
                tenant_id=org_id,
                actor_id=g.current_user_id,
                action='data_access',
                resource=f'endpoint:{request.endpoint}',
                metadata={
                    'method': request.method,
                    'path': request.path,
                    'user_agent': request.headers.get('User-Agent', ''),
                    'timestamp': datetime.now(timezone.utc).isoformat()
                }
            )
        
        # Ensure secure transmission
        if not request.is_secure:
            # In production, this should be enforced at the reverse proxy level
            # For development, we'll just log a warning
            app_logger.warning(f"Insecure request to {request.endpoint} - HTTPS required for HIPAA compliance")


# Global compliance enforcement middleware instance
compliance_enforcement = ComplianceEnforcementMiddleware()


def require_compliance_enforcement(f):
    """Decorator for enforcing compliance requirements."""
    return compliance_enforcement.enforce_compliance(f)
