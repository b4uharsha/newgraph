"""Tests for execution models."""

from datetime import UTC, datetime

from graph_olap_schemas import ExecutionStatus

from wrapper.models.execution import AlgorithmExecution, ExecutionProgress


class TestAlgorithmExecution:
    """Tests for AlgorithmExecution model."""

    def test_algorithm_execution_basic(self):
        """Test basic AlgorithmExecution creation."""
        now = datetime.now(UTC)
        execution = AlgorithmExecution(
            execution_id="exec-123",
            algorithm_name="pagerank",
            algorithm_type="networkx",
            status=ExecutionStatus.RUNNING,
            started_at=now,
            user_id="user-123",
            user_name="test-user",
        )

        assert execution.execution_id == "exec-123"
        assert execution.algorithm_name == "pagerank"
        assert execution.algorithm_type == "networkx"
        assert execution.status == ExecutionStatus.RUNNING
        assert execution.started_at == now
        assert execution.user_id == "user-123"
        assert execution.user_name == "test-user"
        assert execution.parameters == {}
        assert execution.result_property is None
        assert execution.error_message is None
        assert execution.node_label is None
        assert execution.nodes_updated is None
        assert execution.duration_ms is None

    def test_is_terminal_completed(self):
        """Test is_terminal for completed execution."""
        now = datetime.now(UTC)
        execution = AlgorithmExecution(
            execution_id="exec-123",
            algorithm_name="pagerank",
            algorithm_type="networkx",
            status=ExecutionStatus.COMPLETED,
            started_at=now,
            user_id="user-123",
            user_name="test-user",
        )

        assert execution.is_terminal() is True

    def test_is_terminal_failed(self):
        """Test is_terminal for failed execution."""
        now = datetime.now(UTC)
        execution = AlgorithmExecution(
            execution_id="exec-123",
            algorithm_name="pagerank",
            algorithm_type="networkx",
            status=ExecutionStatus.FAILED,
            started_at=now,
            user_id="user-123",
            user_name="test-user",
        )

        assert execution.is_terminal() is True

    def test_is_terminal_cancelled(self):
        """Test is_terminal for cancelled execution."""
        now = datetime.now(UTC)
        execution = AlgorithmExecution(
            execution_id="exec-123",
            algorithm_name="pagerank",
            algorithm_type="networkx",
            status=ExecutionStatus.CANCELLED,
            started_at=now,
            user_id="user-123",
            user_name="test-user",
        )

        assert execution.is_terminal() is True

    def test_is_terminal_running(self):
        """Test is_terminal for running execution."""
        now = datetime.now(UTC)
        execution = AlgorithmExecution(
            execution_id="exec-123",
            algorithm_name="pagerank",
            algorithm_type="networkx",
            status=ExecutionStatus.RUNNING,
            started_at=now,
            user_id="user-123",
            user_name="test-user",
        )

        assert execution.is_terminal() is False

    def test_is_terminal_pending(self):
        """Test is_terminal for pending execution."""
        now = datetime.now(UTC)
        execution = AlgorithmExecution(
            execution_id="exec-123",
            algorithm_name="pagerank",
            algorithm_type="networkx",
            status=ExecutionStatus.PENDING,
            started_at=now,
            user_id="user-123",
            user_name="test-user",
        )

        assert execution.is_terminal() is False

    def test_to_api_dict_basic(self):
        """Test to_api_dict with minimal fields."""
        now = datetime.now(UTC)
        execution = AlgorithmExecution(
            execution_id="exec-123",
            algorithm_name="pagerank",
            algorithm_type="networkx",
            status=ExecutionStatus.RUNNING,
            started_at=now,
            user_id="user-123",
            user_name="test-user",
        )

        result = execution.to_api_dict()

        assert result["execution_id"] == "exec-123"
        assert result["algorithm_name"] == "pagerank"
        assert result["algorithm_type"] == "networkx"
        assert result["status"] == "running"
        assert result["started_at"] == now.isoformat()
        assert result["user_id"] == "user-123"
        assert result["user_name"] == "test-user"
        assert result["parameters"] == {}
        assert "completed_at" not in result
        assert "result_property" not in result
        assert "error_message" not in result
        assert "node_label" not in result
        assert "nodes_updated" not in result
        assert "duration_ms" not in result

    def test_to_api_dict_with_completed_at(self):
        """Test to_api_dict includes completed_at when present."""
        now = datetime.now(UTC)
        completed = datetime.now(UTC)
        execution = AlgorithmExecution(
            execution_id="exec-123",
            algorithm_name="pagerank",
            algorithm_type="networkx",
            status=ExecutionStatus.COMPLETED,
            started_at=now,
            completed_at=completed,
            user_id="user-123",
            user_name="test-user",
        )

        result = execution.to_api_dict()

        assert result["completed_at"] == completed.isoformat()

    def test_to_api_dict_with_result_property(self):
        """Test to_api_dict includes result_property when present."""
        now = datetime.now(UTC)
        execution = AlgorithmExecution(
            execution_id="exec-123",
            algorithm_name="pagerank",
            algorithm_type="networkx",
            status=ExecutionStatus.COMPLETED,
            started_at=now,
            user_id="user-123",
            user_name="test-user",
            result_property="pagerank_score",
        )

        result = execution.to_api_dict()

        assert result["result_property"] == "pagerank_score"

    def test_to_api_dict_with_error_message(self):
        """Test to_api_dict includes error_message when present."""
        now = datetime.now(UTC)
        execution = AlgorithmExecution(
            execution_id="exec-123",
            algorithm_name="pagerank",
            algorithm_type="networkx",
            status=ExecutionStatus.FAILED,
            started_at=now,
            user_id="user-123",
            user_name="test-user",
            error_message="Algorithm failed: out of memory",
        )

        result = execution.to_api_dict()

        assert result["error_message"] == "Algorithm failed: out of memory"

    def test_to_api_dict_with_node_label(self):
        """Test to_api_dict includes node_label when present."""
        now = datetime.now(UTC)
        execution = AlgorithmExecution(
            execution_id="exec-123",
            algorithm_name="pagerank",
            algorithm_type="networkx",
            status=ExecutionStatus.COMPLETED,
            started_at=now,
            user_id="user-123",
            user_name="test-user",
            node_label="Person",
        )

        result = execution.to_api_dict()

        assert result["node_label"] == "Person"

    def test_to_api_dict_with_nodes_updated(self):
        """Test to_api_dict includes nodes_updated when present."""
        now = datetime.now(UTC)
        execution = AlgorithmExecution(
            execution_id="exec-123",
            algorithm_name="pagerank",
            algorithm_type="networkx",
            status=ExecutionStatus.COMPLETED,
            started_at=now,
            user_id="user-123",
            user_name="test-user",
            nodes_updated=1000,
        )

        result = execution.to_api_dict()

        assert result["nodes_updated"] == 1000

    def test_to_api_dict_with_nodes_updated_zero(self):
        """Test to_api_dict includes nodes_updated even when zero."""
        now = datetime.now(UTC)
        execution = AlgorithmExecution(
            execution_id="exec-123",
            algorithm_name="pagerank",
            algorithm_type="networkx",
            status=ExecutionStatus.COMPLETED,
            started_at=now,
            user_id="user-123",
            user_name="test-user",
            nodes_updated=0,
        )

        result = execution.to_api_dict()

        assert result["nodes_updated"] == 0

    def test_to_api_dict_with_duration_ms(self):
        """Test to_api_dict includes duration_ms when present."""
        now = datetime.now(UTC)
        execution = AlgorithmExecution(
            execution_id="exec-123",
            algorithm_name="pagerank",
            algorithm_type="networkx",
            status=ExecutionStatus.COMPLETED,
            started_at=now,
            user_id="user-123",
            user_name="test-user",
            duration_ms=5000,
        )

        result = execution.to_api_dict()

        assert result["duration_ms"] == 5000

    def test_to_api_dict_with_duration_ms_zero(self):
        """Test to_api_dict includes duration_ms even when zero."""
        now = datetime.now(UTC)
        execution = AlgorithmExecution(
            execution_id="exec-123",
            algorithm_name="pagerank",
            algorithm_type="networkx",
            status=ExecutionStatus.COMPLETED,
            started_at=now,
            user_id="user-123",
            user_name="test-user",
            duration_ms=0,
        )

        result = execution.to_api_dict()

        assert result["duration_ms"] == 0

    def test_to_api_dict_with_all_fields(self):
        """Test to_api_dict with all optional fields populated."""
        now = datetime.now(UTC)
        completed = datetime.now(UTC)
        execution = AlgorithmExecution(
            execution_id="exec-123",
            algorithm_name="pagerank",
            algorithm_type="networkx",
            status=ExecutionStatus.COMPLETED,
            started_at=now,
            completed_at=completed,
            user_id="user-123",
            user_name="test-user",
            parameters={"alpha": 0.85, "max_iter": 100},
            result_property="pagerank_score",
            node_label="Person",
            nodes_updated=1500,
            duration_ms=7500,
        )

        result = execution.to_api_dict()

        assert result["execution_id"] == "exec-123"
        assert result["completed_at"] == completed.isoformat()
        assert result["parameters"] == {"alpha": 0.85, "max_iter": 100}
        assert result["result_property"] == "pagerank_score"
        assert result["node_label"] == "Person"
        assert result["nodes_updated"] == 1500
        assert result["duration_ms"] == 7500


class TestExecutionProgress:
    """Tests for ExecutionProgress model."""

    def test_execution_progress_basic(self):
        """Test basic ExecutionProgress creation."""
        progress = ExecutionProgress(
            execution_id="exec-123",
            phase="computing",
        )

        assert progress.execution_id == "exec-123"
        assert progress.phase == "computing"
        assert progress.progress_percent is None
        assert progress.message is None

    def test_execution_progress_with_percent(self):
        """Test ExecutionProgress with progress percentage."""
        progress = ExecutionProgress(
            execution_id="exec-123",
            phase="computing",
            progress_percent=50,
        )

        assert progress.progress_percent == 50

    def test_execution_progress_with_message(self):
        """Test ExecutionProgress with message."""
        progress = ExecutionProgress(
            execution_id="exec-123",
            phase="computing",
            message="Processing batch 5 of 10",
        )

        assert progress.message == "Processing batch 5 of 10"

    def test_execution_progress_all_fields(self):
        """Test ExecutionProgress with all fields."""
        progress = ExecutionProgress(
            execution_id="exec-123",
            phase="writing",
            progress_percent=75,
            message="Writing results to database",
        )

        assert progress.execution_id == "exec-123"
        assert progress.phase == "writing"
        assert progress.progress_percent == 75
        assert progress.message == "Writing results to database"
