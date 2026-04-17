"""Tests for AlgorithmManager and NetworkXManager.

These are critical execution paths that interface with the graph instance.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from graph_olap.exceptions import (
    AlgorithmFailedError,
    AlgorithmTimeoutError,
    NotFoundError,
    ServerError,
    ValidationError,
)
from graph_olap.instance.algorithms import AlgorithmManager, NetworkXManager

# =============================================================================
# Test Fixtures
# =============================================================================


def make_execution_response(
    execution_id: str = "exec-123",
    algorithm: str = "pagerank",
    status: str = "completed",
    nodes_updated: int | None = 1000,
    error_message: str | None = None,
    result: dict | None = None,
) -> dict:
    """Create a mock execution response.

    Matches wrapper API format (no data wrapper, uses algorithm_name).
    """
    return {
        "execution_id": execution_id,
        "algorithm_name": algorithm,
        "algorithm_type": "native",
        "status": status,
        "started_at": "2025-01-15T10:00:00Z",
        "completed_at": "2025-01-15T10:01:00Z" if status == "completed" else None,
        "nodes_updated": nodes_updated,
        "error_message": error_message,
        "result": result,
    }


def make_error_response(status_code: int, code: str, message: str) -> MagicMock:
    """Create a mock error response."""
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = {
        "error": {
            "code": code,
            "message": message,
            "details": {},
        }
    }
    response.text = message
    return response


# =============================================================================
# AlgorithmManager Tests
# =============================================================================


class TestAlgorithmManagerPageRank:
    """Tests for AlgorithmManager.pagerank()."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_client: MagicMock) -> AlgorithmManager:
        return AlgorithmManager(mock_client)

    def test_pagerank_success_immediate(self, manager: AlgorithmManager, mock_client: MagicMock):
        """PageRank returns completed execution immediately."""
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = make_execution_response(
            algorithm="pagerank", status="completed", nodes_updated=5000
        )

        result = manager.pagerank("Customer", "pr_score", wait=True)

        assert result.algorithm == "pagerank"
        assert result.status == "completed"
        assert result.nodes_updated == 5000

        # Check request - uses dynamic endpoint /algo/{algorithm}
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/algo/pagerank"
        body = call_args[1]["json"]
        assert body["node_label"] == "Customer"
        assert body["result_property"] == "pr_score"
        assert body["parameters"]["damping_factor"] == 0.85

    def test_pagerank_custom_params(self, manager: AlgorithmManager, mock_client: MagicMock):
        """PageRank accepts custom parameters."""
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = make_execution_response()

        manager.pagerank(
            "Account",
            "score",
            damping=0.9,
            max_iterations=200,
            tolerance=1e-8,
            wait=False,
        )

        body = mock_client.post.call_args[1]["json"]
        assert body["parameters"]["damping_factor"] == 0.9
        assert body["parameters"]["max_iterations"] == 200
        assert body["parameters"]["tolerance"] == 1e-8

    def test_pagerank_no_wait(self, manager: AlgorithmManager, mock_client: MagicMock):
        """PageRank with wait=False returns immediately without polling."""
        mock_client.post.return_value.status_code = 202
        mock_client.post.return_value.json.return_value = make_execution_response(status="running")

        result = manager.pagerank("Customer", "pr_score", wait=False)

        assert result.status == "running"
        # Should not poll for status
        mock_client.get.assert_not_called()


class TestAlgorithmManagerConnectedComponents:
    """Tests for AlgorithmManager.connected_components()."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_client: MagicMock) -> AlgorithmManager:
        return AlgorithmManager(mock_client)

    def test_connected_components_success(self, manager: AlgorithmManager, mock_client: MagicMock):
        """Connected components returns component count."""
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = make_execution_response(
            algorithm="connected_components",
            status="completed",
            result={"component_count": 42},
        )

        result = manager.connected_components("Account", "component_id")

        assert result.algorithm == "connected_components"
        assert result.result == {"component_count": 42}


class TestAlgorithmManagerShortestPath:
    """Tests for AlgorithmManager.shortest_path()."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_client: MagicMock) -> AlgorithmManager:
        return AlgorithmManager(mock_client)

    def test_shortest_path_found(self, manager: AlgorithmManager, mock_client: MagicMock):
        """Shortest path returns path when found."""
        path_result = {
            "path": ["node-1", "node-2", "node-3"],
            "length": 2,
        }
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = make_execution_response(
            algorithm="shortest_path",
            status="completed",
            result=path_result,
        )

        result = manager.shortest_path("node-1", "node-3")

        assert result.result == path_result
        body = mock_client.post.call_args[1]["json"]
        # shortest_path uses flat body structure, not nested in parameters
        assert body["source_id"] == "node-1"
        assert body["target_id"] == "node-3"

    def test_shortest_path_with_filters(self, manager: AlgorithmManager, mock_client: MagicMock):
        """Shortest path accepts relationship type filters."""
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = make_execution_response()

        manager.shortest_path(
            "a",
            "b",
            relationship_types=["KNOWS", "WORKS_WITH"],
            max_depth=5,
        )

        body = mock_client.post.call_args[1]["json"]
        # shortest_path uses flat body structure, not nested in parameters
        assert body["relationship_types"] == ["KNOWS", "WORKS_WITH"]
        assert body["max_depth"] == 5


class TestAlgorithmManagerLouvain:
    """Tests for AlgorithmManager.louvain()."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_client: MagicMock) -> AlgorithmManager:
        return AlgorithmManager(mock_client)

    def test_louvain_default_resolution(self, manager: AlgorithmManager, mock_client: MagicMock):
        """Louvain uses default resolution of 1.0 (no params sent)."""
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = make_execution_response()

        manager.louvain("Customer", "community_id")

        body = mock_client.post.call_args[1]["json"]
        # Default resolution=1.0 doesn't send params
        assert "parameters" not in body or body.get("parameters") is None

    def test_louvain_high_resolution(self, manager: AlgorithmManager, mock_client: MagicMock):
        """Louvain with high resolution produces more communities."""
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = make_execution_response()

        manager.louvain("Customer", "community_id", resolution=2.0)

        body = mock_client.post.call_args[1]["json"]
        assert body["parameters"]["resolution"] == 2.0


class TestAlgorithmManagerLabelPropagation:
    """Tests for AlgorithmManager.label_propagation()."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_client: MagicMock) -> AlgorithmManager:
        return AlgorithmManager(mock_client)

    def test_label_propagation_success(self, manager: AlgorithmManager, mock_client: MagicMock):
        """Label propagation completes successfully."""
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = make_execution_response(
            algorithm="label_propagation"
        )

        result = manager.label_propagation("Entity", "label")

        assert result.algorithm == "label_propagation"
        body = mock_client.post.call_args[1]["json"]
        assert body["parameters"]["max_iterations"] == 100


class TestAlgorithmManagerTriangleCount:
    """Tests for AlgorithmManager.triangle_count()."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_client: MagicMock) -> AlgorithmManager:
        return AlgorithmManager(mock_client)

    def test_triangle_count_success(self, manager: AlgorithmManager, mock_client: MagicMock):
        """Triangle count completes successfully."""
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = make_execution_response(
            algorithm="triangle_count",
            result={"total_triangles": 1234},
        )

        result = manager.triangle_count("Person", "triangles")

        assert result.algorithm == "triangle_count"


class TestAlgorithmManagerWaitForCompletion:
    """Tests for algorithm polling and wait behavior."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_client: MagicMock) -> AlgorithmManager:
        return AlgorithmManager(mock_client)

    def test_wait_polls_until_complete(self, manager: AlgorithmManager, mock_client: MagicMock):
        """Wait polls status until algorithm completes."""
        # Initial POST returns running
        mock_client.post.return_value.status_code = 202
        mock_client.post.return_value.json.return_value = make_execution_response(status="running")

        # GET returns running, then completed
        running_response = MagicMock()
        running_response.status_code = 200
        running_response.json.return_value = make_execution_response(status="running")

        completed_response = MagicMock()
        completed_response.status_code = 200
        completed_response.json.return_value = make_execution_response(status="completed")

        mock_client.get.side_effect = [running_response, completed_response]

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.sleep", lambda x: None)
            result = manager.pagerank("Customer", "pr", timeout=60)

        assert result.status == "completed"
        assert mock_client.get.call_count == 2

    def test_wait_raises_on_failure(self, manager: AlgorithmManager, mock_client: MagicMock):
        """Wait raises AlgorithmFailedError when algorithm fails."""
        mock_client.post.return_value.status_code = 202
        mock_client.post.return_value.json.return_value = make_execution_response(status="running")

        failed_response = MagicMock()
        failed_response.status_code = 200
        failed_response.json.return_value = make_execution_response(
            status="failed",
            error_message="Out of memory",
        )
        mock_client.get.return_value = failed_response

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.sleep", lambda x: None)
            with pytest.raises(AlgorithmFailedError, match="Out of memory"):
                manager.pagerank("Customer", "pr")

    def test_wait_raises_on_timeout(self, manager: AlgorithmManager, mock_client: MagicMock):
        """Wait raises AlgorithmTimeoutError when timeout exceeded."""
        mock_client.post.return_value.status_code = 202
        mock_client.post.return_value.json.return_value = make_execution_response(status="running")

        running_response = MagicMock()
        running_response.status_code = 200
        running_response.json.return_value = make_execution_response(status="running")
        mock_client.get.return_value = running_response

        # Simulate time passing beyond timeout
        call_count = [0]

        def mock_time():
            call_count[0] += 1
            return call_count[0] * 100  # Each call is 100s later

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.time", mock_time)
            mp.setattr("time.sleep", lambda x: None)
            with pytest.raises(AlgorithmTimeoutError, match="did not complete"):
                manager.pagerank("Customer", "pr", timeout=10)


class TestAlgorithmManagerErrorHandling:
    """Tests for error handling in AlgorithmManager."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_client: MagicMock) -> AlgorithmManager:
        return AlgorithmManager(mock_client)

    def test_handles_validation_error(self, manager: AlgorithmManager, mock_client: MagicMock):
        """Handles validation errors from the API."""
        mock_client.post.return_value = make_error_response(
            422, "VALIDATION_ERROR", "Invalid node label"
        )

        with pytest.raises(ValidationError, match="Invalid node label"):
            manager.pagerank("InvalidLabel", "pr")

    def test_handles_not_found_error(self, manager: AlgorithmManager, mock_client: MagicMock):
        """Handles not found errors."""
        mock_client.post.return_value = make_error_response(
            404, "NOT_FOUND", "Node label not found"
        )

        with pytest.raises(NotFoundError, match="Node label not found"):
            manager.pagerank("NonExistent", "pr")

    def test_handles_server_error(self, manager: AlgorithmManager, mock_client: MagicMock):
        """Handles server errors."""
        mock_client.post.return_value = make_error_response(
            500, "INTERNAL_ERROR", "Database connection failed"
        )

        with pytest.raises(ServerError, match="Database connection failed"):
            manager.pagerank("Customer", "pr")

    def test_handles_malformed_error_response(
        self, manager: AlgorithmManager, mock_client: MagicMock
    ):
        """Handles error responses without standard error format."""
        response = MagicMock()
        response.status_code = 500
        response.json.side_effect = Exception("Not JSON")
        response.text = "Internal Server Error"
        mock_client.post.return_value = response

        with pytest.raises(ServerError, match="Internal Server Error"):
            manager.pagerank("Customer", "pr")

    def test_handles_empty_error_response(self, manager: AlgorithmManager, mock_client: MagicMock):
        """Handles error responses with empty body."""
        response = MagicMock()
        response.status_code = 503
        response.json.side_effect = Exception("Empty")
        response.text = ""
        mock_client.post.return_value = response

        with pytest.raises(ServerError, match="HTTP 503"):
            manager.pagerank("Customer", "pr")


# =============================================================================
# NetworkXManager Tests
# =============================================================================


class TestNetworkXManagerAlgorithms:
    """Tests for NetworkXManager.algorithms()."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_client: MagicMock) -> NetworkXManager:
        return NetworkXManager(mock_client)

    def test_list_all_algorithms(self, manager: NetworkXManager, mock_client: MagicMock):
        """Lists all available NetworkX algorithms."""
        algorithms_list = [
            {"name": "pagerank", "category": "centrality"},
            {"name": "betweenness_centrality", "category": "centrality"},
            {"name": "louvain_communities", "category": "community"},
        ]
        # Wrapper returns AlgorithmListResponse with 'algorithms' field
        mock_client.get.return_value.json.return_value = {"algorithms": algorithms_list}

        result = manager.algorithms()

        assert len(result) == 3
        mock_client.get.assert_called_once_with("/networkx/algorithms", params={})

    def test_list_algorithms_by_category(self, manager: NetworkXManager, mock_client: MagicMock):
        """Lists algorithms filtered by category."""
        centrality_algos = [
            {"name": "pagerank", "category": "centrality"},
            {"name": "betweenness_centrality", "category": "centrality"},
        ]
        mock_client.get.return_value.json.return_value = {"algorithms": centrality_algos}

        result = manager.algorithms(category="centrality")

        assert len(result) == 2
        mock_client.get.assert_called_once_with(
            "/networkx/algorithms", params={"category": "centrality"}
        )


class TestNetworkXManagerAlgorithmInfo:
    """Tests for NetworkXManager.algorithm_info()."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_client: MagicMock) -> NetworkXManager:
        return NetworkXManager(mock_client)

    def test_get_algorithm_info(self, manager: NetworkXManager, mock_client: MagicMock):
        """Gets detailed info for specific algorithm."""
        algo_info = {
            "name": "betweenness_centrality",
            "category": "centrality",
            "description": "Compute betweenness centrality for nodes.",
            "parameters": [
                {"name": "k", "type": "int", "required": False, "default": None},
            ],
        }
        # Wrapper returns AlgorithmInfoResponse directly (no data wrapper)
        mock_client.get.return_value.json.return_value = algo_info

        result = manager.algorithm_info("betweenness_centrality")

        assert result["name"] == "betweenness_centrality"
        assert len(result["parameters"]) == 1
        mock_client.get.assert_called_once_with("/networkx/algorithms/betweenness_centrality")


class TestNetworkXManagerRun:
    """Tests for NetworkXManager.run()."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_client: MagicMock) -> NetworkXManager:
        return NetworkXManager(mock_client)

    def test_run_algorithm_success(self, manager: NetworkXManager, mock_client: MagicMock):
        """Run returns completed execution."""
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = make_execution_response(
            algorithm="katz_centrality", status="completed"
        )

        result = manager.run(
            "katz_centrality",
            node_label="Customer",
            property_name="katz",
            params={"alpha": 0.1},
        )

        assert result.algorithm == "katz_centrality"
        assert result.status == "completed"

        # Uses dynamic endpoint /networkx/{algorithm}
        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/networkx/katz_centrality"
        body = call_args[1]["json"]
        assert body["node_label"] == "Customer"
        assert body["result_property"] == "katz"
        assert body["parameters"]["alpha"] == 0.1

    def test_run_without_node_label(self, manager: NetworkXManager, mock_client: MagicMock):
        """Run works for graph-level algorithms without node label."""
        mock_client.post.return_value.status_code = 200
        mock_client.post.return_value.json.return_value = make_execution_response(
            algorithm="is_connected",
            result={"connected": True},
        )

        result = manager.run("is_connected")

        body = mock_client.post.call_args[1]["json"]
        assert "node_label" not in body
        assert "result_property" not in body


class TestNetworkXManagerConvenienceMethods:
    """Tests for NetworkXManager convenience methods."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        client = MagicMock()
        client.post.return_value.status_code = 200
        client.post.return_value.json.return_value = make_execution_response()
        return client

    @pytest.fixture
    def manager(self, mock_client: MagicMock) -> NetworkXManager:
        return NetworkXManager(mock_client)

    def test_degree_centrality(self, manager: NetworkXManager, mock_client: MagicMock):
        """degree_centrality convenience method."""
        manager.degree_centrality("Node", "degree")

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/networkx/degree_centrality"
        body = call_args[1]["json"]
        assert body["node_label"] == "Node"
        assert body["result_property"] == "degree"

    def test_betweenness_centrality_with_k(self, manager: NetworkXManager, mock_client: MagicMock):
        """betweenness_centrality with k parameter for sampling."""
        manager.betweenness_centrality("Node", "betweenness", k=100)

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/networkx/betweenness_centrality"
        body = call_args[1]["json"]
        assert body["parameters"]["k"] == 100

    def test_betweenness_centrality_without_k(
        self, manager: NetworkXManager, mock_client: MagicMock
    ):
        """betweenness_centrality without k (full computation)."""
        manager.betweenness_centrality("Node", "betweenness")

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/networkx/betweenness_centrality"
        body = call_args[1]["json"]
        assert "parameters" not in body or body.get("parameters") == {}

    def test_closeness_centrality(self, manager: NetworkXManager, mock_client: MagicMock):
        """closeness_centrality convenience method."""
        manager.closeness_centrality("Node", "closeness")

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/networkx/closeness_centrality"

    def test_eigenvector_centrality(self, manager: NetworkXManager, mock_client: MagicMock):
        """eigenvector_centrality with max_iter parameter."""
        manager.eigenvector_centrality("Node", "eigenvector", max_iter=500)

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/networkx/eigenvector_centrality"
        body = call_args[1]["json"]
        assert body["parameters"]["max_iter"] == 500

    def test_clustering_coefficient(self, manager: NetworkXManager, mock_client: MagicMock):
        """clustering_coefficient convenience method."""
        manager.clustering_coefficient("Node", "clustering")

        call_args = mock_client.post.call_args
        assert call_args[0][0] == "/networkx/clustering"


class TestNetworkXManagerWaitForCompletion:
    """Tests for NetworkXManager polling behavior."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_client: MagicMock) -> NetworkXManager:
        return NetworkXManager(mock_client)

    def test_polls_correct_endpoint(self, manager: NetworkXManager, mock_client: MagicMock):
        """Polls NetworkX-specific status endpoint."""
        mock_client.post.return_value.status_code = 202
        mock_client.post.return_value.json.return_value = make_execution_response(
            execution_id="nx-exec-456", status="running"
        )

        completed_response = MagicMock()
        completed_response.status_code = 200
        completed_response.json.return_value = make_execution_response(
            execution_id="nx-exec-456", status="completed"
        )
        mock_client.get.return_value = completed_response

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.sleep", lambda x: None)
            manager.run("degree_centrality", "Node", "deg")

        # Should poll /networkx/status/
        mock_client.get.assert_called_with("/networkx/status/nx-exec-456")

    def test_raises_on_timeout(self, manager: NetworkXManager, mock_client: MagicMock):
        """Raises AlgorithmTimeoutError on timeout."""
        mock_client.post.return_value.status_code = 202
        mock_client.post.return_value.json.return_value = make_execution_response(status="running")

        running_response = MagicMock()
        running_response.status_code = 200
        running_response.json.return_value = make_execution_response(status="running")
        mock_client.get.return_value = running_response

        call_count = [0]

        def mock_time():
            call_count[0] += 1
            return call_count[0] * 100

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.time", mock_time)
            mp.setattr("time.sleep", lambda x: None)
            with pytest.raises(AlgorithmTimeoutError, match="NetworkX algorithm"):
                manager.run("slow_algo", "Node", "prop", timeout=10)


class TestNetworkXManagerErrorHandling:
    """Tests for error handling in NetworkXManager."""

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def manager(self, mock_client: MagicMock) -> NetworkXManager:
        return NetworkXManager(mock_client)

    def test_handles_unknown_algorithm(self, manager: NetworkXManager, mock_client: MagicMock):
        """Handles unknown algorithm error."""
        mock_client.post.return_value = make_error_response(
            422, "VALIDATION_ERROR", "Unknown algorithm: nonexistent_algo"
        )

        with pytest.raises(ValidationError, match="Unknown algorithm"):
            manager.run("nonexistent_algo", "Node", "prop")

    def test_handles_algorithm_failure(self, manager: NetworkXManager, mock_client: MagicMock):
        """Handles algorithm execution failure."""
        mock_client.post.return_value.status_code = 202
        mock_client.post.return_value.json.return_value = make_execution_response(status="running")

        failed_response = MagicMock()
        failed_response.status_code = 200
        failed_response.json.return_value = make_execution_response(
            status="failed",
            error_message="Graph is not connected",
        )
        mock_client.get.return_value = failed_response

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.sleep", lambda x: None)
            with pytest.raises(AlgorithmFailedError, match="Graph is not connected"):
                manager.run("shortest_path", "Node", "path")

    def test_handles_status_check_error(self, manager: NetworkXManager, mock_client: MagicMock):
        """Handles error during status check."""
        mock_client.post.return_value.status_code = 202
        mock_client.post.return_value.json.return_value = make_execution_response(status="running")

        mock_client.get.return_value = make_error_response(
            500, "INTERNAL_ERROR", "Instance crashed"
        )

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("time.sleep", lambda x: None)
            with pytest.raises(ServerError, match="Instance crashed"):
                manager.run("degree_centrality", "Node", "deg")
