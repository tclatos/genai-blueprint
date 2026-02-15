"""Path setup for Deer-flow backend imports.

Deer-flow's backend is not pip-installable (no build-system in pyproject.toml).
This module adds the deer-flow backend directory to sys.path so that its internal
imports (e.g., `from src.agents import make_lead_agent`) work correctly.

The deer-flow backend is expected at one of:
    1. ext/deer-flow/backend  (cloned via `make deer-flow-install`)
    2. DEER_FLOW_PATH env var pointing to deer-flow root
    3. ../deer-flow/backend   (sibling directory)
"""

import os
import sys
from pathlib import Path

from loguru import logger

# Cached path once resolved
_deer_flow_backend_path: Path | None = None


def get_deer_flow_backend_path() -> Path:
    """Resolve the deer-flow backend directory path.

    Search order:
        1. DEER_FLOW_PATH environment variable (points to deer-flow root)
        2. ext/deer-flow/backend (relative to project root)
        3. ../deer-flow/backend (sibling to project)
        4. /home/tcl/ext_prj/deer-flow/backend (development fallback)

    Returns:
        Path to the deer-flow backend directory

    Raises:
        FileNotFoundError: If deer-flow backend cannot be found
    """
    global _deer_flow_backend_path
    if _deer_flow_backend_path is not None:
        return _deer_flow_backend_path

    project_root = Path.cwd()
    candidates = []

    # 1. Environment variable
    env_path = os.environ.get("DEER_FLOW_PATH")
    if env_path:
        candidates.append(Path(env_path) / "backend")

    # 2. ext/deer-flow inside project
    candidates.append(project_root / "ext" / "deer-flow" / "backend")

    # 3. Sibling directory
    candidates.append(project_root.parent / "deer-flow" / "backend")

    # 4. Development fallback
    candidates.append(Path.home() / "ext_prj" / "deer-flow" / "backend")

    for candidate in candidates:
        if candidate.exists() and (candidate / "src" / "__init__.py").exists():
            _deer_flow_backend_path = candidate.resolve()
            logger.info(f"Deer-flow backend found at: {_deer_flow_backend_path}")
            return _deer_flow_backend_path

    searched = "\n  ".join(str(c) for c in candidates)
    raise FileNotFoundError(
        f"Deer-flow backend not found. Searched:\n  {searched}\n\n"
        "Install with: make deer-flow-install\n"
        "Or set DEER_FLOW_PATH environment variable to the deer-flow root directory."
    )


def setup_deer_flow_path() -> Path:
    """Add deer-flow backend to sys.path if not already present.

    This must be called before any `from src.xxx import ...` deer-flow imports.

    Returns:
        Path to the deer-flow backend directory
    """
    backend_path = get_deer_flow_backend_path()
    path_str = str(backend_path)

    if path_str not in sys.path:
        sys.path.insert(0, path_str)
        logger.debug(f"Added deer-flow backend to sys.path: {path_str}")

    # Also set DEER_FLOW_CONFIG_PATH if not already set
    # (deer-flow config.yaml is expected in the parent directory)
    if "DEER_FLOW_CONFIG_PATH" not in os.environ:
        config_path = backend_path.parent / "config.yaml"
        if config_path.exists():
            os.environ["DEER_FLOW_CONFIG_PATH"] = str(config_path)
            logger.debug(f"Set DEER_FLOW_CONFIG_PATH to: {config_path}")

    return backend_path
