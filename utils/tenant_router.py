import logging
from flask import has_request_context
from flask_jwt_extended import current_user
import mongoengine

logger = logging.getLogger(__name__)


class TenantConnectionRouter:
    """
    Foundation for true 'Database-per-Tenant' sharding.
    Resolves an autonomous MongoDB connection string based on the active JWT's organization context.
    Currently defaults to 'default' (Shared-Database mode), preparing the application layer
    for horizontal single-tenant physical separation without code rewrites.
    """

    @classmethod
    def get_tenant_db_alias(cls, organization_id: str = None) -> str:
        """
        Determines the current active database connection alias.
        """
        from flask import g, has_request_context
        
        if has_request_context() and hasattr(g, "tenant_db_alias") and g.tenant_db_alias:
            return g.tenant_db_alias

        org_id = organization_id
        if not org_id and has_request_context() and current_user:
            org_id = getattr(current_user, "organization_id", None)

        if org_id:
            connection_alias = f"conn_{org_id}"
            from mongoengine.connection import _connections
            if connection_alias in _connections:
                return connection_alias

        return mongoengine.DEFAULT_CONNECTION_NAME

    @classmethod
    def switch_context(cls, organization_id: str):
        """
        Context manager generator mock to manually swap active connections
        during background worker executions (e.g. Celery indexing tasks).
        """
        alias = cls.get_tenant_db_alias(organization_id)
        # Using mongoengine.context_managers.switch_db
        from mongoengine.context_managers import switch_db

        # Implementation returns the context manager wrapping BaseDocument.
        # This requires overriding the global default or passing the model explicitly.
        # Currently a stub to signal future integration boundaries.
        pass


tenant_router = TenantConnectionRouter()
