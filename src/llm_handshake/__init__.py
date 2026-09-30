"""A small, dependency-free LLM endpoint diagnostic library."""

__version__ = "0.1.0"

from .config import Config
from .runner import run_checks

__all__ = ["Config", "run_checks", "__version__"]
