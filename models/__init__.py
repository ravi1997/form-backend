"""
models/__init__.py
Consolidated model imports for the reorganized model structure.
"""

# Import base classes and choices first
from .base import *  # noqa: F401,F403

# Import core models
from .identity import *  # noqa: F401,F403
from .auth import *  # noqa: F401,F403
from .components import *  # noqa: F401,F403
from .form import *  # noqa: F401,F403
from .response import *  # noqa: F401,F403
from .analysis import *  # noqa: F401,F403
from .dashboard import *  # noqa: F401,F403
from .workflow import *  # noqa: F401,F403
from .notification import *  # noqa: F401,F403
from .integration import *  # noqa: F401,F403
from .system import *  # noqa: F401,F403
from .utility import *  # noqa: F401,F403

# Legacy imports for backward compatibility (will be deprecated)
# Taxonomy models removed - they were consolidated into other models