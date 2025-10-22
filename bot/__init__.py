"""
Main bot package.

This file makes the 'bot' directory a Python package and can be used
to expose key components from sub-modules for easier access.
"""

from .client import app

# This makes `from bot import app` possible elsewhere in the project.
__all__ = ["app"]
