"""Demo bootstrap helper.

Provides a small helper to ensure the project root is on sys.path so demos
can import the top-level `src` package regardless of how they're executed.

This module is intentionally loaded via importlib in demo scripts so it can
be located by file path (works even when running a demo as a script).
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional


def ensure_project_root_on_path(caller_file: Optional[str] = None) -> str:
    """Ensure the project root (parent of the demos folder) is on sys.path.

    Args:
        caller_file: Path to the calling file (usually pass __file__). If None,
            this function will use its own file location which still works if
            loaded directly, but callers should pass their __file__ for
            clarity.

    Returns:
        The string path that was ensured on sys.path.
    """
    if caller_file is None:
        caller_file = __file__

    project_root = Path(caller_file).resolve().parents[1]
    project_root_str = str(project_root)
    if project_root_str not in sys.path:
        # Insert at front so it has priority for imports during demos
        sys.path.insert(0, project_root_str)

    return project_root_str
