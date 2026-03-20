import mongoengine
from flask import request, g
from config.settings import settings
import logging

logger = logging.getLogger(__name__)

def setup_tenant_db(app):
    """
    Middleware that dynamically registers and switches MongoDB connections 
    based on the 'organization_id' in the request header.
    Provides physical database-level isolation between tenants.
    """
    
    @app.before_request
    def before_request():
        # 1. Identify Tenant
        org_id = request.headers.get("X-Organization-ID")
        
        # 2. Skip for public/un-authenticated routes if needed
        if not org_id:
             return
             
        # 3. Dynamic Connection Strategy
        # Connection name derived from organization ID
        db_name = f"tenant_db_{org_id}"
        connection_alias = f"conn_{org_id}"
        
        # 4. Connection Pool Management
        # Check if already registered to avoid overhead
        from mongoengine.connection import _connections
        if connection_alias not in _connections:
            # Construct tenant-specific URI
            # Note: In production, these URIs would be fetched from a 
            # secure 'Master Tenant Registry' (Postgres) indexed by org_id.
            base_uri_parts = settings.MONGODB_URI.split("/")
            # Assuming format: mongodb://user:pass@host:port/default_db?...
            base_uri = "/".join(base_uri_parts[:-1])
            tenant_uri = f"{base_uri}/{db_name}"
            
            logger.info(f"Platform: Dynamically registering physical isolation for tenant: {org_id}")
            mongoengine.register_connection(
                alias=connection_alias,
                host=tenant_uri,
                serverSelectionTimeoutMS=2000
            )
            
        # 5. Context Injection
        # Store the alias in flask.g for Services to consume
        g.tenant_db_alias = connection_alias
        
    return app
