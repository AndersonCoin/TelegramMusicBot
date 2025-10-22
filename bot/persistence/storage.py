"""Storage backend abstraction."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pathlib import Path
import json
import asyncio

class StorageBackend(ABC):
    """Abstract storage backend."""
    
    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Get value by key."""
        pass
    
    @abstractmethod
    async def set(self, key: str, value: Any) -> bool:
        """Set value for key."""
        pass
    
    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete key."""
        pass
    
    @abstractmethod
    async def get_all(self) -> Dict[str, Any]:
        """Get all key-value pairs."""
        pass

class TinyDBBackend(StorageBackend):
    """TinyDB storage backend."""
    
    def __init__(self, db_path: str = "data/bot.json"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, Any] = {}
        self._load()
    
    def _load(self):
        """Load data from file."""
        if self.db_path.exists():
            try:
                with open(self.db_path, "r") as f:
                    self._data = json.load(f)
            except:
                self._data = {}
    
    def _save(self):
        """Save data to file."""
        with open(self.db_path, "w") as f:
            json.dump(self._data, f, indent=2)
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value by key."""
        return self._data.get(key)
    
    async def set(self, key: str, value: Any) -> bool:
        """Set value for key."""
        self._data[key] = value
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._save)
        return True
    
    async def delete(self, key: str) -> bool:
        """Delete key."""
        if key in self._data:
            del self._data[key]
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._save)
            return True
        return False
    
    async def get_all(self) -> Dict[str, Any]:
        """Get all key-value pairs."""
        return self._data.copy()
