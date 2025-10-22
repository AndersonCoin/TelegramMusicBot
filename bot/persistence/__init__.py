"""
Persistence layer package.

Handles saving and retrieving data, such as playback state and user preferences.
"""

from .storage import playback_storage, language_storage
from .state import save_playback_state, get_playback_state, clear_playback_state

__all__ = [
    "playback_storage",
    "language_storage",
    "save_playback_state",
    "get_playback_state",
    "clear_playback_state",
]
