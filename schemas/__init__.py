"""
schemas/__init__.py
Consolidated schema imports for request/response validation.
"""

# Import all schema modules
from .auth_schemas import *  # noqa: F401,F403
from .form_schemas import *  # noqa: F401,F403
from .analysis_schemas import *  # noqa: F401,F403
from .dashboard_schemas import *  # noqa: F401,F403
from .common_schemas import *  # noqa: F401,F403