from collections import OrderedDict
from threading import RLock

import mongoengine
from flask import request, g
from config.settings import settings
import logging

logger = logging.getLogger(__name__)

MAX_ACTIVE_TENANT_POOLS = 50
_tenant_pool_lock = RLock()
_tenant_pool_lru = OrderedDict()
_tenant_pool_ref_counts = {}


def _mark_pool_access(connection_alias: str) -> None:
    with _tenant_pool_lock:
        _tenant_pool_lru.pop(connection_alias, None)
        _tenant_pool_lru[connection_alias] = None


def _increment_pool_ref(connection_alias: str) -> None:
    with _tenant_pool_lock:
        _tenant_pool_ref_counts[connection_alias] = (
            _tenant_pool_ref_counts.get(connection_alias, 0) + 1
        )


def _decrement_pool_ref(connection_alias: str) -> None:
    with _tenant_pool_lock:
        if connection_alias not in _tenant_pool_ref_counts:
            return
        next_count = _tenant_pool_ref_counts[connection_alias] - 1
        if next_count <= 0:
            _tenant_pool_ref_counts.pop(connection_alias, None)
        else:
            _tenant_pool_ref_counts[connection_alias] = next_count


def _evict_idle_pools() -> None:
    from mongoengine.connection import _connections

    with _tenant_pool_lock:
        while len(_tenant_pool_lru) > MAX_ACTIVE_TENANT_POOLS:
            evicted_alias = None
            for alias in list(_tenant_pool_lru.keys()):
                if _tenant_pool_ref_counts.get(alias, 0) == 0:
                    evicted_alias = alias
                    break

            if evicted_alias is None:
                logger.warning(
                    "Tenant pool cache reached limit but no idle pools were available for eviction"
                )
                return

            _tenant_pool_lru.pop(evicted_alias, None)
            _tenant_pool_ref_counts.pop(evicted_alias, None)

            logger.info("Evicting idle tenant connection pool: %s", evicted_alias)
            mongoengine.disconnect(alias=evicted_alias)


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

        with _tenant_pool_lock:
            if connection_alias not in _connections:
                # Construct tenant-specific URI
                # Note: In production, these URIs would be fetched from a
                # secure 'Master Tenant Registry' (Postgres) indexed by org_id.
                base_uri_parts = settings.MONGODB_URI.split("/")
                # Assuming format: mongodb://user:pass@host:port/default_db?...
                base_uri = "/".join(base_uri_parts[:-1])
                tenant_uri = f"{base_uri}/{db_name}"

                logger.info(
                    "Platform: Dynamically registering physical isolation for tenant: %s",
                    org_id,
                )
                mongoengine.register_connection(
                    alias=connection_alias, host=tenant_uri, serverSelectionTimeoutMS=2000
                )

            _mark_pool_access(connection_alias)
            _evict_idle_pools()

        # 5. Context Injection
        # Store the alias in flask.g for Services to consume
        g.tenant_db_alias = connection_alias
        _increment_pool_ref(connection_alias)

    @app.teardown_request
    def teardown_request(exception):
        connection_alias = getattr(g, "tenant_db_alias", None)
        if connection_alias:
            _decrement_pool_ref(connection_alias)

    return app
