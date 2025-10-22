"""
Core logic package.

Contains the essential components for music playback and queue management.
"""

from .queue import queue_manager, Track
from .player import player

__all__ = ["queue_manager", "Track", "player"]
