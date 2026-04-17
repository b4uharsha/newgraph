"""Algorithm registry for unified algorithm management.

Provides a central registry for both native Ryugraph algorithms and
NetworkX algorithms with a unified interface for discovery and execution.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from graph_olap_schemas import AlgorithmCategory, AlgorithmType

from wrapper.logging import get_logger

if TYPE_CHECKING:
    from wrapper.services.database import DatabaseService

logger = get_logger(__name__)


@dataclass(frozen=True)
class AlgorithmParameter:
    """Definition of an algorithm parameter."""

    name: str
    type: str
    required: bool = True
    default: Any = None
    description: str = ""


@dataclass(frozen=True)
class AlgorithmInfo:
    """Information about a registered algorithm."""

    name: str
    type: AlgorithmType
    category: AlgorithmCategory
    description: str = ""
    long_description: str = ""
    parameters: tuple[AlgorithmParameter, ...] = field(default_factory=tuple)
    returns: str = ""
    node_output: bool = True  # Whether results are written to node properties


class AlgorithmExecutor(Protocol):
    """Protocol for algorithm executors."""

    async def execute(
        self,
        db_service: DatabaseService,
        node_label: str | None,
        edge_type: str | None,
        result_property: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute the algorithm.

        Args:
            db_service: Database service for graph access.
            node_label: Target node label (None = all nodes).
            edge_type: Target edge type (None = all edges).
            result_property: Property name to store results.
            parameters: Algorithm-specific parameters.

        Returns:
            Execution result with nodes_updated, duration_ms, etc.
        """
        ...


class AlgorithmRegistry:
    """Central registry for algorithms.

    Provides unified access to both native Ryugraph algorithms and
    dynamically discovered NetworkX algorithms.
    """

    def __init__(self) -> None:
        """Initialize the registry."""
        self._native_algorithms: dict[str, AlgorithmInfo] = {}
        self._native_executors: dict[str, AlgorithmExecutor] = {}
        self._networkx_algorithms: dict[str, AlgorithmInfo] = {}

        logger.debug("AlgorithmRegistry initialized")

    def register_native(
        self,
        info: AlgorithmInfo,
        executor: AlgorithmExecutor,
    ) -> None:
        """Register a native Ryugraph algorithm.

        Args:
            info: Algorithm information.
            executor: Algorithm executor instance.
        """
        if info.type != AlgorithmType.NATIVE:
            raise ValueError(f"Expected native algorithm, got {info.type}")

        self._native_algorithms[info.name] = info
        self._native_executors[info.name] = executor

        logger.debug("Registered native algorithm", name=info.name, category=info.category)

    def register_networkx(self, info: AlgorithmInfo) -> None:
        """Register a NetworkX algorithm.

        Args:
            info: Algorithm information.
        """
        if info.type != AlgorithmType.NETWORKX:
            raise ValueError(f"Expected networkx algorithm, got {info.type}")

        self._networkx_algorithms[info.name] = info

        logger.debug("Registered NetworkX algorithm", name=info.name, category=info.category)

    def get_algorithm(
        self, name: str, algo_type: AlgorithmType | None = None
    ) -> AlgorithmInfo | None:
        """Get algorithm info by name.

        Args:
            name: Algorithm name.
            algo_type: Optional type filter.

        Returns:
            Algorithm info or None if not found.
        """
        if algo_type == AlgorithmType.NATIVE or algo_type is None:
            if name in self._native_algorithms:
                return self._native_algorithms[name]

        if algo_type == AlgorithmType.NETWORKX or algo_type is None:
            if name in self._networkx_algorithms:
                return self._networkx_algorithms[name]

        return None

    def get_native_executor(self, name: str) -> AlgorithmExecutor | None:
        """Get executor for a native algorithm.

        Args:
            name: Algorithm name.

        Returns:
            Executor or None if not found.
        """
        return self._native_executors.get(name)

    def list_algorithms(
        self,
        algo_type: AlgorithmType | None = None,
        category: AlgorithmCategory | None = None,
        search: str | None = None,
    ) -> list[AlgorithmInfo]:
        """List available algorithms.

        Args:
            algo_type: Filter by algorithm type.
            category: Filter by category.
            search: Search string for name/description.

        Returns:
            List of matching algorithm infos.
        """
        results: list[AlgorithmInfo] = []

        # Collect algorithms
        if algo_type != AlgorithmType.NETWORKX:
            results.extend(self._native_algorithms.values())
        if algo_type != AlgorithmType.NATIVE:
            results.extend(self._networkx_algorithms.values())

        # Filter by category
        if category is not None:
            results = [a for a in results if a.category == category]

        # Filter by search string
        if search:
            search_lower = search.lower()
            results = [
                a
                for a in results
                if search_lower in a.name.lower() or search_lower in a.description.lower()
            ]

        # Sort by name
        results.sort(key=lambda a: a.name)

        return results

    def list_native(self) -> list[AlgorithmInfo]:
        """List all native algorithms."""
        return list(self._native_algorithms.values())

    def list_networkx(self) -> list[AlgorithmInfo]:
        """List all NetworkX algorithms."""
        return list(self._networkx_algorithms.values())

    @property
    def native_count(self) -> int:
        """Number of registered native algorithms."""
        return len(self._native_algorithms)

    @property
    def networkx_count(self) -> int:
        """Number of registered NetworkX algorithms."""
        return len(self._networkx_algorithms)

    @property
    def total_count(self) -> int:
        """Total number of registered algorithms."""
        return self.native_count + self.networkx_count


# Global registry instance
_registry: AlgorithmRegistry | None = None


def get_registry() -> AlgorithmRegistry:
    """Get the global algorithm registry.

    Returns:
        The singleton AlgorithmRegistry instance.
    """
    global _registry
    if _registry is None:
        _registry = AlgorithmRegistry()
    return _registry


def reset_registry() -> None:
    """Reset the global registry (for testing)."""
    global _registry
    _registry = None
