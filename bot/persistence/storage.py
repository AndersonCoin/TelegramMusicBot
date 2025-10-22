"""Storage abstraction layer."""

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

from tinydb import TinyDB, Query

from config import config

logger = logging.getLogger(__name__)


class Storage(ABC):
    """Abstract storage interface."""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get value by key."""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Dict[str, Any]) -> bool:
        """Set value for key."""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete key."""
        pass
    
    @abstractmethod
    async def get_all(self) -> List[Dict[str, Any]]:
        """Get all values."""
        pass
    
    @abstractmethod
    async def clear(self) -> bool:
        """Clear all data."""
        pass


class TinyDBStorage(Storage):
    """TinyDB storage implementation."""
    
    def __init__(self, db_path: str = "data/db.json"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = TinyDB(self.db_path)
        self.table = self.db.table("states")
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get value by key."""
        try:
            Record = Query()
            result = self.table.search(Record.key == key)
            return result[0]["value"] if result else None
        except Exception as e:
            logger.error(f"Storage get error: {e}")
            return None
    
    async def set(self, key: str, value: Dict[str, Any]) -> bool:
        """Set value for key."""
        try:
            Record = Query()
            self.table.upsert(
                {"key": key, "value": value},
                Record.key == key
            )
            return True
        except Exception as e:
            logger.error(f"Storage set error: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key."""
        try:
            Record = Query()
            self.table.remove(Record.key == key)
            return True
        except Exception as e:
            logger.error(f"Storage delete error: {e}")
            return False
    
    async def get_all(self) -> List[Dict[str, Any]]:
        """Get all values."""
        try:
            return [record["value"] for record in self.table.all()]
        except Exception as e:
            logger.error(f"Storage get_all error: {e}")
            return []
    
    async def clear(self) -> bool:
        """Clear all data."""
        try:
            self.table.truncate()
            return True
        except Exception as e:
            logger.error(f"Storage clear error: {e}")
            return False


def get_storage() -> Storage:
    """Get storage instance based on config."""
    if config.STATE_BACKEND == "tinydb":
        return TinyDBStorage()
    else:
        # Default to TinyDB for MVP
        return TinyDBStorage()

# Global storage instance
storage = get_storage()
