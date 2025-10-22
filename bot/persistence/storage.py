"""Storage abstraction layer."""

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

from tinydb import TinyDB, Query

from config import config

logger = logging.getLogger(__name__)


class StorageBackend(ABC):
    """Abstract storage backend."""
    
    @abstractmethod
    async def initialize(self) -> None:
        """Initialize storage."""
        pass
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get value by key."""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Dict[str, Any]) -> None:
        """Set value for key."""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete key."""
        pass
    
    @abstractmethod
    async def get_all(self) -> List[Dict[str, Any]]:
        """Get all values."""
        pass
    
    @abstractmethod
    async def clear(self) -> None:
        """Clear all data."""
        pass


class TinyDBBackend(StorageBackend):
    """TinyDB storage backend."""
    
    def __init__(self):
        self.db_path = Path("data/db.json")
        self.db: Optional[TinyDB] = None
    
    async def initialize(self) -> None:
        """Initialize TinyDB."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.db = TinyDB(self.db_path)
        logger.info("TinyDB initialized")
    
    async def get(self, key: str) -> Optional[Dict[str, Any]]:
        """Get value by key."""
        if not self.db:
            return None
        
        Record = Query()
        result = self.db.search(Record.key == key)
        return result[0]["value"] if result else None
    
    async def set(self, key: str, value: Dict[str, Any]) -> None:
        """Set value for key."""
        if not self.db:
            return
        
        Record = Query()
        self.db.upsert({"key": key, "value": value}, Record.key == key)
    
    async def delete(self, key: str) -> None:
        """Delete key."""
        if not self.db:
            return
        
        Record = Query()
        self.db.remove(Record.key == key)
    
    async def get_all(self) -> List[Dict[str, Any]]:
        """Get all values."""
        if not self.db:
            return []
        
        return [record["value"] for record in self.db.all()]
    
    async def clear(self) -> None:
        """Clear all data."""
        if self.db:
            self.db.truncate()


def get_storage() -> StorageBackend:
    """Get storage backend based on config."""
    if config.STATE_BACKEND == "tinydb":
        return TinyDBBackend()
    else:
        # Default to TinyDB for MVP
        return TinyDBBackend()

# Global storage instance
storage = get_storage()
