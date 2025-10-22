"""Persistence module initialization."""

from .storage import storage
from .state import StateManager

__all__ = ['storage', 'StateManager']
