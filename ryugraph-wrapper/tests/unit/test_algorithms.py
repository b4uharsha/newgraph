"""Unit tests for the algorithms module."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from wrapper.algorithms.native import (
    KCoreAlgorithm,
    LouvainAlgorithm,
    PageRankAlgorithm,
    StronglyConnectedComponentsAlgorithm,
    StronglyConnectedComponentsKosarajuAlgorithm,
    WeaklyConnectedComponentsAlgorithm,
    get_native_algorithm,
    register_native_algorithms,
)
from wrapper.algorithms.networkx import (
    discover_algorithm,
    get_algorithm_info,
    list_algorithms,
)
from wrapper.algorithms.registry import (
    AlgorithmCategory,
    AlgorithmInfo,
    AlgorithmParameter,
    AlgorithmRegistry,
    AlgorithmType,
    get_registry,
    reset_registry,
)


class TestAlgorithmRegistry:
    """Tests for AlgorithmRegistry."""

    @pytest.fixture(autouse=True)
    def reset_global_registry(self) -> None:
        """Reset the global registry before each test."""
        reset_registry()

    @pytest.fixture
    def registry(self) -> AlgorithmRegistry:
        """Create a fresh registry."""
        return AlgorithmRegistry()

    @pytest.fixture
    def sample_native_info(self) -> AlgorithmInfo:
        """Create sample native algorithm info."""
        return AlgorithmInfo(
            name="test_native",
            type=AlgorithmType.NATIVE,
            category=AlgorithmCategory.CENTRALITY,
            description="Test native algorithm",
            parameters=(
                AlgorithmParameter(
                    name="param1",
                    type="int",
                    required=True,
                    description="Test parameter",
                ),
            ),
        )

    @pytest.fixture
    def sample_networkx_info(self) -> AlgorithmInfo:
        """Create sample NetworkX algorithm info."""
        return AlgorithmInfo(
            name="test_networkx",
            type=AlgorithmType.NETWORKX,
            category=AlgorithmCategory.COMMUNITY,
            description="Test NetworkX algorithm",
        )

    # =========================================================================
    # Registration Tests
    # =========================================================================

    @pytest.mark.unit
    def test_register_native_algorithm(
        self,
        registry: AlgorithmRegistry,
        sample_native_info: AlgorithmInfo,
    ) -> None:
        """Can register a native algorithm."""
        executor = MagicMock()
        registry.register_native(sample_native_info, executor)

        assert registry.native_count == 1
        assert registry.get_algorithm("test_native") == sample_native_info

    @pytest.mark.unit
    def test_register_native_wrong_type_raises(
        self,
        registry: AlgorithmRegistry,
        sample_networkx_info: AlgorithmInfo,
    ) -> None:
        """Registering NetworkX as native raises error."""
        executor = MagicMock()
        with pytest.raises(ValueError, match="Expected native"):
            registry.register_native(sample_networkx_info, executor)

    @pytest.mark.unit
    def test_register_networkx_algorithm(
        self,
        registry: AlgorithmRegistry,
        sample_networkx_info: AlgorithmInfo,
    ) -> None:
        """Can register a NetworkX algorithm."""
        registry.register_networkx(sample_networkx_info)

        assert registry.networkx_count == 1
        assert registry.get_algorithm("test_networkx") == sample_networkx_info

    @pytest.mark.unit
    def test_register_networkx_wrong_type_raises(
        self,
        registry: AlgorithmRegistry,
        sample_native_info: AlgorithmInfo,
    ) -> None:
        """Registering native as NetworkX raises error."""
        with pytest.raises(ValueError, match="Expected networkx"):
            registry.register_networkx(sample_native_info)

    # =========================================================================
    # Retrieval Tests
    # =========================================================================

    @pytest.mark.unit
    def test_get_algorithm_by_name(
        self,
        registry: AlgorithmRegistry,
        sample_native_info: AlgorithmInfo,
        sample_networkx_info: AlgorithmInfo,
    ) -> None:
        """Can retrieve algorithm by name."""
        registry.register_native(sample_native_info, MagicMock())
        registry.register_networkx(sample_networkx_info)

        assert registry.get_algorithm("test_native") == sample_native_info
        assert registry.get_algorithm("test_networkx") == sample_networkx_info
        assert registry.get_algorithm("nonexistent") is None

    @pytest.mark.unit
    def test_get_algorithm_with_type_filter(
        self,
        registry: AlgorithmRegistry,
        sample_native_info: AlgorithmInfo,
        sample_networkx_info: AlgorithmInfo,
    ) -> None:
        """Can filter by algorithm type."""
        registry.register_native(sample_native_info, MagicMock())
        registry.register_networkx(sample_networkx_info)

        # Filter by native - should not find networkx
        assert registry.get_algorithm("test_networkx", AlgorithmType.NATIVE) is None
        assert registry.get_algorithm("test_native", AlgorithmType.NATIVE) == sample_native_info

    @pytest.mark.unit
    def test_get_native_executor(
        self,
        registry: AlgorithmRegistry,
        sample_native_info: AlgorithmInfo,
    ) -> None:
        """Can retrieve executor for native algorithm."""
        executor = MagicMock()
        registry.register_native(sample_native_info, executor)

        assert registry.get_native_executor("test_native") == executor
        assert registry.get_native_executor("nonexistent") is None

    # =========================================================================
    # Listing Tests
    # =========================================================================

    @pytest.mark.unit
    def test_list_all_algorithms(
        self,
        registry: AlgorithmRegistry,
        sample_native_info: AlgorithmInfo,
        sample_networkx_info: AlgorithmInfo,
    ) -> None:
        """Can list all algorithms."""
        registry.register_native(sample_native_info, MagicMock())
        registry.register_networkx(sample_networkx_info)

        all_algos = registry.list_algorithms()
        assert len(all_algos) == 2
        names = [a.name for a in all_algos]
        assert "test_native" in names
        assert "test_networkx" in names

    @pytest.mark.unit
    def test_list_by_type(
        self,
        registry: AlgorithmRegistry,
        sample_native_info: AlgorithmInfo,
        sample_networkx_info: AlgorithmInfo,
    ) -> None:
        """Can filter list by type."""
        registry.register_native(sample_native_info, MagicMock())
        registry.register_networkx(sample_networkx_info)

        native_only = registry.list_algorithms(algo_type=AlgorithmType.NATIVE)
        assert len(native_only) == 1
        assert native_only[0].name == "test_native"

        networkx_only = registry.list_algorithms(algo_type=AlgorithmType.NETWORKX)
        assert len(networkx_only) == 1
        assert networkx_only[0].name == "test_networkx"

    @pytest.mark.unit
    def test_list_by_category(
        self,
        registry: AlgorithmRegistry,
        sample_native_info: AlgorithmInfo,
        sample_networkx_info: AlgorithmInfo,
    ) -> None:
        """Can filter list by category."""
        registry.register_native(sample_native_info, MagicMock())
        registry.register_networkx(sample_networkx_info)

        centrality_only = registry.list_algorithms(category=AlgorithmCategory.CENTRALITY)
        assert len(centrality_only) == 1
        assert centrality_only[0].category == AlgorithmCategory.CENTRALITY

    @pytest.mark.unit
    def test_list_with_search(
        self,
        registry: AlgorithmRegistry,
        sample_native_info: AlgorithmInfo,
    ) -> None:
        """Can search algorithms by name/description."""
        registry.register_native(sample_native_info, MagicMock())

        # Search by name
        results = registry.list_algorithms(search="native")
        assert len(results) == 1

        # Search by description
        results = registry.list_algorithms(search="Test")
        assert len(results) == 1

        # No match
        results = registry.list_algorithms(search="xyz123")
        assert len(results) == 0

    # =========================================================================
    # Global Registry Tests
    # =========================================================================

    @pytest.mark.unit
    def test_get_registry_singleton(self) -> None:
        """get_registry returns singleton."""
        reg1 = get_registry()
        reg2 = get_registry()
        assert reg1 is reg2

    @pytest.mark.unit
    def test_reset_registry(self) -> None:
        """reset_registry clears the singleton."""
        reg1 = get_registry()
        reset_registry()
        reg2 = get_registry()
        assert reg1 is not reg2


class TestNativeAlgorithms:
    """Tests for native algorithm implementations."""

    @pytest.fixture
    def mock_db_service(self) -> MagicMock:
        """Create mock database service."""
        service = MagicMock()
        service.execute_query = AsyncMock()
        return service

    # =========================================================================
    # PageRank Tests
    # =========================================================================

    @pytest.mark.unit
    def test_pagerank_info(self) -> None:
        """PageRank has correct info."""
        algo = PageRankAlgorithm()
        info = algo.info

        assert info.name == "pagerank"
        assert info.type == AlgorithmType.NATIVE
        assert info.category == AlgorithmCategory.CENTRALITY
        assert len(info.parameters) == 3

    @pytest.mark.unit
    async def test_pagerank_execute(self, mock_db_service: MagicMock) -> None:
        """PageRank executes successfully using algo extension."""
        # Mock ensure_property_exists
        mock_db_service.ensure_property_exists = AsyncMock()

        # Mock query results for algo extension pattern
        # Pattern: project_graph -> page_rank -> 3x write results -> drop_projected_graph
        mock_db_service.execute_query.side_effect = [
            {"rows": [], "columns": []},  # project_graph
            {
                "rows": [[0, 0.2], [1, 0.3], [2, 0.5]],
                "columns": ["node_offset", "rank"],
            },  # page_rank
            {"rows": [], "columns": []},  # write result 1
            {"rows": [], "columns": []},  # write result 2
            {"rows": [], "columns": []},  # write result 3
            {"rows": [], "columns": []},  # drop_projected_graph
        ]

        algo = PageRankAlgorithm()
        result = await algo.execute(
            db_service=mock_db_service,
            node_label="Person",
            edge_type="KNOWS",
            result_property="pagerank",
            parameters={"max_iterations": 20},
        )

        assert result["nodes_updated"] == 3
        assert "duration_ms" in result
        assert result["converged"] is True

    @pytest.mark.unit
    async def test_pagerank_requires_node_label_and_edge_type(
        self, mock_db_service: MagicMock
    ) -> None:
        """PageRank requires both node_label and edge_type."""
        from wrapper.exceptions import AlgorithmError

        algo = PageRankAlgorithm()

        with pytest.raises(AlgorithmError, match="requires both"):
            await algo.execute(
                db_service=mock_db_service,
                node_label=None,
                edge_type="KNOWS",
                result_property="pr",
                parameters={},
            )

    # =========================================================================
    # WCC Tests
    # =========================================================================

    @pytest.mark.unit
    def test_wcc_info(self) -> None:
        """WCC has correct info."""
        algo = WeaklyConnectedComponentsAlgorithm()
        info = algo.info

        assert info.name == "wcc"
        assert info.category == AlgorithmCategory.COMMUNITY

    @pytest.mark.unit
    async def test_wcc_execute(self, mock_db_service: MagicMock) -> None:
        """WCC executes successfully using algo extension."""
        mock_db_service.ensure_property_exists = AsyncMock()
        # Pattern: project_graph -> wcc -> 3x write results -> drop_projected_graph
        mock_db_service.execute_query.side_effect = [
            {"rows": [], "columns": []},  # project_graph
            {"rows": [[0, 1], [1, 1], [2, 2]], "columns": ["node_offset", "group_id"]},  # wcc
            {"rows": [], "columns": []},  # write result 1
            {"rows": [], "columns": []},  # write result 2
            {"rows": [], "columns": []},  # write result 3
            {"rows": [], "columns": []},  # drop_projected_graph
        ]

        algo = WeaklyConnectedComponentsAlgorithm()
        result = await algo.execute(
            db_service=mock_db_service,
            node_label="Node",
            edge_type="EDGE",
            result_property="component",
            parameters={},
        )

        assert result["nodes_updated"] == 3
        assert result["components"] == 2  # 2 distinct group_ids

    # =========================================================================
    # SCC Tests
    # =========================================================================

    @pytest.mark.unit
    def test_scc_info(self) -> None:
        """SCC has correct info."""
        algo = StronglyConnectedComponentsAlgorithm()
        info = algo.info

        assert info.name == "scc"
        assert info.category == AlgorithmCategory.COMMUNITY

    @pytest.mark.unit
    def test_scc_kosaraju_info(self) -> None:
        """SCC Kosaraju has correct info."""
        algo = StronglyConnectedComponentsKosarajuAlgorithm()
        info = algo.info

        assert info.name == "scc_kosaraju"
        assert info.category == AlgorithmCategory.COMMUNITY
        assert len(info.parameters) == 0  # No parameters

    # =========================================================================
    # Louvain Tests
    # =========================================================================

    @pytest.mark.unit
    def test_louvain_info(self) -> None:
        """Louvain has correct info."""
        algo = LouvainAlgorithm()
        info = algo.info

        assert info.name == "louvain"
        assert info.category == AlgorithmCategory.COMMUNITY
        assert len(info.parameters) == 2  # max_phases, max_iterations

    # =========================================================================
    # K-Core Tests
    # =========================================================================

    @pytest.mark.unit
    def test_kcore_info(self) -> None:
        """K-Core has correct info."""
        algo = KCoreAlgorithm()
        info = algo.info

        assert info.name == "kcore"
        assert info.category == AlgorithmCategory.COMMUNITY
        assert len(info.parameters) == 0  # No parameters

    # =========================================================================
    # Algorithm Discovery Tests
    # =========================================================================

    @pytest.mark.unit
    def test_get_native_algorithm(self) -> None:
        """Can retrieve native algorithm by name."""
        algo = get_native_algorithm("pagerank")
        assert algo is not None
        assert algo.info.name == "pagerank"

        algo = get_native_algorithm("nonexistent")
        assert algo is None

    @pytest.mark.unit
    def test_register_native_algorithms(self) -> None:
        """register_native_algorithms populates registry."""
        reset_registry()
        register_native_algorithms()

        registry = get_registry()
        assert registry.native_count >= 6  # At least our 6 algorithms


class TestNetworkXAlgorithms:
    """Tests for NetworkX algorithm discovery and execution."""

    # =========================================================================
    # Discovery Tests
    # =========================================================================

    @pytest.mark.unit
    def test_discover_pagerank(self) -> None:
        """Can discover PageRank algorithm."""
        result = discover_algorithm("pagerank")
        assert result is not None

        func, module_path = result
        assert callable(func)
        assert "pagerank" in module_path.lower()

    @pytest.mark.unit
    def test_discover_nonexistent(self) -> None:
        """Returns None for nonexistent algorithm."""
        result = discover_algorithm("nonexistent_algorithm_xyz")
        assert result is None

    @pytest.mark.unit
    def test_discover_betweenness_centrality(self) -> None:
        """Can discover betweenness_centrality."""
        result = discover_algorithm("betweenness_centrality")
        assert result is not None

    # =========================================================================
    # Info Extraction Tests
    # =========================================================================

    @pytest.mark.unit
    def test_get_algorithm_info_pagerank(self) -> None:
        """Can get info for PageRank."""
        info = get_algorithm_info("pagerank")
        assert info is not None
        assert info.name == "pagerank"
        assert info.type == AlgorithmType.NETWORKX
        assert info.category == AlgorithmCategory.CENTRALITY
        assert len(info.parameters) > 0

    @pytest.mark.unit
    def test_get_algorithm_info_extracts_parameters(self) -> None:
        """Algorithm info includes parameter details."""
        info = get_algorithm_info("pagerank")
        assert info is not None

        # Should have alpha (damping) parameter
        param_names = [p.name for p in info.parameters]
        assert "alpha" in param_names

    @pytest.mark.unit
    def test_get_algorithm_info_nonexistent(self) -> None:
        """Returns None for nonexistent algorithm."""
        info = get_algorithm_info("nonexistent_xyz")
        assert info is None

    # =========================================================================
    # Listing Tests
    # =========================================================================

    @pytest.mark.unit
    def test_list_algorithms_returns_results(self) -> None:
        """list_algorithms returns available algorithms."""
        algos = list_algorithms()
        assert len(algos) > 0

        # Should include some known algorithms
        names = [a.name for a in algos]
        # At least pagerank should be present
        assert "pagerank" in names

    @pytest.mark.unit
    def test_list_algorithms_filter_by_category(self) -> None:
        """Can filter by category."""
        centrality_algos = list_algorithms(category=AlgorithmCategory.CENTRALITY)
        assert len(centrality_algos) > 0
        for algo in centrality_algos:
            assert algo.category == AlgorithmCategory.CENTRALITY

    @pytest.mark.unit
    def test_list_algorithms_search(self) -> None:
        """Can search by name/description."""
        results = list_algorithms(search="pagerank")
        assert len(results) >= 1
        assert any("pagerank" in a.name for a in results)


class TestAlgorithmWriteback:
    """Tests for algorithm result write-back."""

    @pytest.fixture
    def mock_db_service(self) -> MagicMock:
        """Create mock database service."""
        service = MagicMock()
        service.execute_query = AsyncMock(return_value={"rows": [[10]], "columns": ["updated"]})
        return service

    @pytest.mark.unit
    async def test_write_node_property(self, mock_db_service: MagicMock) -> None:
        """Can write node property values."""
        from wrapper.algorithms.writeback import write_node_property

        values = {"node1": 0.5, "node2": 0.3, "node3": 0.2}
        result = await write_node_property(
            db_service=mock_db_service,
            node_label="Person",
            property_name="score",
            values=values,
        )

        assert result == 10
        mock_db_service.execute_query.assert_called()

    @pytest.mark.unit
    async def test_write_node_property_empty(self, mock_db_service: MagicMock) -> None:
        """Empty values dict returns 0."""
        from wrapper.algorithms.writeback import write_node_property

        result = await write_node_property(
            db_service=mock_db_service,
            node_label=None,
            property_name="test",
            values={},
        )

        assert result == 0
        mock_db_service.execute_query.assert_not_called()

    @pytest.mark.unit
    async def test_initialize_node_property(self, mock_db_service: MagicMock) -> None:
        """Can initialize node property."""
        from wrapper.algorithms.writeback import initialize_node_property

        result = await initialize_node_property(
            db_service=mock_db_service,
            node_label="Person",
            property_name="visited",
            default_value=False,
        )

        assert result == 10
        mock_db_service.execute_query.assert_called_once()

    @pytest.mark.unit
    async def test_remove_node_property(self, mock_db_service: MagicMock) -> None:
        """Can remove node property."""
        from wrapper.algorithms.writeback import remove_node_property

        result = await remove_node_property(
            db_service=mock_db_service,
            node_label="Person",
            property_name="temp",
        )

        assert result == 10
        # Verify REMOVE clause was used
        call_args = mock_db_service.execute_query.call_args
        assert "REMOVE" in call_args[0][0]
