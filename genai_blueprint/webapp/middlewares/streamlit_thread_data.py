"""Streamlit Thread Data Middleware - provides workspace paths without runtime.context.

This middleware replicates ThreadDataMiddleware's functionality but works in Streamlit
by getting thread_id from LangGraph's config instead of runtime.context.

Enables Python-based file I/O skills (ppt-generation, chart-visualization, etc.)
that run in the Streamlit process and write files to the workspace.

Does NOT enable sandbox-based tools (bash, docker) which require container infrastructure.
"""

import os
from pathlib import Path
from typing import Any

from loguru import logger


class ThreadDataState(dict):
    """Thread data paths provided to skills."""

    workspace_path: str
    uploads_path: str
    outputs_path: str


class StreamlitThreadDataMiddleware:
    """Provides workspace paths for file I/O skills in Streamlit context.

    Unlike deer-flow's ThreadDataMiddleware, this doesn't require runtime.context.
    Instead, it gets thread_id from LangGraph's config which is always available.

    Example usage in skills:
        ```python
        workspace = state["thread_data"]["workspace_path"]
        output_file = os.path.join(workspace, "presentation.pptx")
        prs.save(output_file)
        ```

    Directory structure created:
        {base_dir}/threads/{thread_id}/user-data/
        ├── workspace/  # Main workspace for generated files
        ├── uploads/    # User uploaded files (future)
        └── outputs/    # Deprecated, use workspace
    """

    def __init__(self, base_dir: str | Path | None = None, lazy_init: bool = False) -> None:
        """Initialize the middleware.

        Args:
            base_dir: Base directory for thread workspaces.
                     Defaults to .deer-flow-streamlit in current working directory.
            lazy_init: If True, only compute paths without creating directories.
                      If False, create directories immediately.
                      Default False (create directories for reliability).
        """
        if base_dir is None:
            base_dir = Path.cwd() / ".deer-flow-streamlit"
        self._base_dir = Path(base_dir)
        self._lazy_init = lazy_init

        # Create base directory
        self._base_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"StreamlitThreadDataMiddleware initialized with base_dir: {self._base_dir}")

    def _get_thread_paths(self, thread_id: str) -> dict[str, str]:
        """Compute paths for a thread's workspace directories.

        Args:
            thread_id: The thread/session ID

        Returns:
            Dictionary with workspace_path, uploads_path, outputs_path
        """
        thread_dir = self._base_dir / "threads" / thread_id / "user-data"

        return {
            "workspace_path": str(thread_dir / "workspace"),
            "uploads_path": str(thread_dir / "uploads"),
            "outputs_path": str(thread_dir / "outputs"),
        }

    def _create_thread_directories(self, thread_id: str) -> dict[str, str]:
        """Create workspace directories for a thread.

        Args:
            thread_id: The thread/session ID

        Returns:
            Dictionary with the created directory paths
        """
        paths = self._get_thread_paths(thread_id)

        # Create all directories
        for path_str in paths.values():
            os.makedirs(path_str, exist_ok=True)

        logger.debug(f"Created workspace directories for thread {thread_id}")
        return paths

    def before_agent(self, state: dict[str, Any], runtime: Any) -> dict[str, Any] | None:
        """Provide workspace paths to the agent before execution.

        Gets thread_id from LangGraph's config instead of runtime.context.

        Args:
            state: Current agent state
            runtime: LangGraph runtime (context may be None, but config is available)

        Returns:
            Update dict with thread_data paths

        Raises:
            ValueError: If thread_id cannot be determined
        """
        # Try to get thread_id from multiple sources
        thread_id = None

        # 1. Try LangGraph's configurable (most reliable)
        if hasattr(runtime, "config") and runtime.config:
            configurable = runtime.config.get("configurable", {})
            thread_id = configurable.get("thread_id")

        # 2. Fallback: try runtime.context if available (deer-flow native)
        if not thread_id and hasattr(runtime, "context") and runtime.context:
            try:
                thread_id = runtime.context.get("thread_id")
            except (AttributeError, TypeError):
                pass

        # 3. Final fallback: use a default thread_id
        if not thread_id:
            thread_id = "streamlit-default"
            logger.warning(
                f"Could not determine thread_id from runtime, using default: {thread_id}. "
                "Files from different sessions may mix."
            )

        # Create or compute paths
        if self._lazy_init:
            paths = self._get_thread_paths(thread_id)
            logger.debug(f"Computed workspace paths for thread {thread_id} (lazy mode)")
        else:
            paths = self._create_thread_directories(thread_id)
            logger.debug(f"Created workspace directories for thread {thread_id}")

        # Add to state
        return {"thread_data": paths}

    def get_workspace_dir(self, thread_id: str) -> Path:
        """Get the workspace directory path for a thread.

        Useful for UI components that need to list/download files.

        Args:
            thread_id: The thread/session ID

        Returns:
            Path to the workspace directory
        """
        paths = self._get_thread_paths(thread_id)
        return Path(paths["workspace_path"])

    def list_workspace_files(self, thread_id: str) -> list[dict[str, Any]]:
        """List all files in a thread's workspace.

        Args:
            thread_id: The thread/session ID

        Returns:
            List of file info dicts with keys: name, path, size, modified
        """
        workspace = self.get_workspace_dir(thread_id)

        if not workspace.exists():
            return []

        files = []
        for file_path in workspace.rglob("*"):
            if file_path.is_file():
                stat = file_path.stat()
                files.append(
                    {
                        "name": file_path.name,
                        "path": str(file_path),
                        "relative_path": str(file_path.relative_to(workspace)),
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                    }
                )

        return sorted(files, key=lambda x: x["modified"], reverse=True)

    def cleanup_old_threads(self, max_age_days: int = 7) -> int:
        """Clean up workspace directories older than specified age.

        Args:
            max_age_days: Maximum age in days before cleanup

        Returns:
            Number of thread directories removed
        """
        import time

        threads_dir = self._base_dir / "threads"
        if not threads_dir.exists():
            return 0

        current_time = time.time()
        max_age_seconds = max_age_days * 86400
        removed_count = 0

        for thread_dir in threads_dir.iterdir():
            if not thread_dir.is_dir():
                continue

            # Check age
            dir_age = current_time - thread_dir.stat().st_mtime
            if dir_age > max_age_seconds:
                import shutil

                try:
                    shutil.rmtree(thread_dir)
                    removed_count += 1
                    logger.info(f"Cleaned up old thread directory: {thread_dir.name}")
                except Exception as e:
                    logger.warning(f"Failed to clean up {thread_dir.name}: {e}")

        return removed_count
