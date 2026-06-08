"""LangChain Runnable registry and management system.

This module implements a centralized registry for managing LangChain Runnables,
providing a unified interface for registration, retrieval, and execution of
various chain components.

Key Features:
- Centralized registry for all Runnable components
- Support for multiple Runnable types (instances, factories, key-based pairs)
- Example-based testing and demonstration
- Dynamic module loading for chain definitions
- Metadata and diagram support for documentation

The registry supports three types of Runnables:
1. Direct Runnable instances
2. Factory functions returning Runnables
3. Key-based callable pairs for parameterized Runnables

Example:
    >>> # Register a new chain
    >>> register_runnable(
    ...     RunnableItem(name="my_chain", runnable=my_chain_instance, examples=[Example(query=["sample query"])])
    ... )

    >>> # Find and execute a chain
    >>> chain = chain_registry.find("my_chain")
    >>> result = chain.invoke("input text")
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from typing import Any

from genai_tk.config_mgmt.config_mngr import global_config
from genai_tk.utils.singleton import once
from langchain_core.runnables import Runnable, RunnableLambda
from loguru import logger
from pydantic import BaseModel, ConfigDict, FilePath


class Example(BaseModel):
    """Defines examples for demonstrating and testing Runnable behavior.

    This class encapsulates example queries and optional file paths for
    demonstration purposes, particularly useful for RAG (Retrieval Augmented Generation)
    scenarios.

    Attributes:
        query (list[str]): List of example queries or prompts
        path (FilePath | None): Optional path to a file containing additional examples or context
    """

    query: list[str]
    path: FilePath | None = None
    # ext: str | None = None


class RunnableItem(BaseModel):
    """A comprehensive wrapper for LangChain Runnable components with metadata and execution capabilities.

    This class encapsulates a LangChain Runnable along with associated metadata and provides
    methods for executing the Runnable with various configurations. It supports multiple
    forms of Runnable definitions and includes demo/testing capabilities.

    Attributes:
        name (str): Unique identifier for the Runnable
        tag (str | None): Optional categorization tag
        runnable (Union[Runnable, Tuple[str, Callable], Callable]): The actual Runnable component,
            which can be:
            - A direct Runnable instance
            - A factory function returning a Runnable
            - A tuple of (key, factory_function) where the function creates a Runnable
              expecting a dict with the specified key
        examples (list[Example]): List of example inputs for testing/demo
        diagram (str | None): Optional diagram showing the Runnable's structure/flow

    Methods:
        get: Retrieve the configured Runnable instance
    """

    name: str
    tag: str | None = None
    runnable: (
        Runnable | tuple[str, Callable[[dict[str, Any]], Runnable]] | Callable[[dict[str, Any]], Runnable]
    )  # Either a Runnable, or ...
    examples: list[Example] = []
    diagram: str | None = None

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def get(self, conf: dict | None = None) -> Runnable:
        if conf is None:
            conf = {"llm": None}
        if isinstance(self.runnable, Runnable):
            runnable = self.runnable
        elif isinstance(self.runnable, Callable):
            runnable = self.runnable(conf)
        elif isinstance(self.runnable, tuple):
            key, func = self.runnable
            func_runnable = ChainRegistry._to_key_param_callable(key, func)
            runnable = func_runnable(conf)
        else:
            raise Exception("unknown or ill-formatted Runnable")
        # print(self.runnable, runnable)
        return runnable


class ChainRegistry(BaseModel):
    registry: list[RunnableItem] = []

    @once
    def instance() -> ChainRegistry:
        """Create Registry instance"""

        return ChainRegistry(registry=[])

    @once
    def load_modules() -> None:
        """Create Registry instance and dynamically load chain modules specified in the configuration.

        This function reads the configuration to find and import modules containing
        chain definitions. It uses the 'chains.modules' configuration
        values to determine which modules to load.
        """
        _ = ChainRegistry.instance()
        modules = global_config().get_list("chains.modules")
        for module in modules:
            try:
                importlib.import_module(module)
                logger.debug(f"load module '{module}'")
            except Exception as ex:
                logger.exception(f"Cannot load module {module}: {ex}")

    def register(self, r: RunnableItem) -> None:
        """Register a new RunnableItem in the global registry."""
        self.registry.append(r)

    def get_runnable_list(self) -> list[RunnableItem]:
        """Retrieve the complete list of registered Runnables."""
        return self.registry

    def find(self, name: str) -> RunnableItem | None:
        """Find a registered Runnable by its name (case-insensitive)."""

        return next((x for x in self.registry if x.name.strip().lower() == name.strip().lower()), None)

    @staticmethod
    def _to_key_param_callable(key: str, function: Callable[[dict[str, Any]], Runnable]) -> Callable[[Any], Runnable]:
        """Convert a key-based function to a callable that works with the Runnable pipeline.

        This helper function transforms a function that expects a configuration dictionary
        and returns a Runnable into a pipeline-compatible function that automatically
        wraps string inputs into the expected dictionary format.

        Args:
            key (str): The dictionary key to use for the input value
            function (Callable): The original function that creates a Runnable

        Returns:
            Callable[[Any], Runnable]: A wrapped function that creates a properly configured Runnable
        """
        return lambda conf: RunnableLambda(lambda x: {key: x}) | function(conf)


def register_runnable(r: RunnableItem) -> None:
    """Register a new RunnableItem in the global registry."""
    registry = ChainRegistry.instance()
    registry.register(r)
