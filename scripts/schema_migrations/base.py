from abc import ABC, abstractmethod
import logging

logger = logging.getLogger(__name__)

class BaseSchemaMigration(ABC):
    """
    Abstract interface for database schema evolution.
    Supports forward (up) and backward (down) migrations.
    """
    
    @property
    @abstractmethod
    def version(self) -> str:
        """Unique version identifier (e.g. '20260319_01')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        pass

    @abstractmethod
    def up(self):
        """Execute the migration logic."""
        pass

    @abstractmethod
    def down(self):
        """Revert the migration logic."""
        pass
