"""Tests for QueryResult conversion and visualization methods."""

from unittest.mock import MagicMock, patch

import pytest

from graph_olap.models.common import QueryResult


class TestQueryResultToPolars:
    """Tests for to_polars() conversion."""

    def test_to_polars_success(self):
        """Test converting to Polars DataFrame."""
        result = QueryResult.from_api_response(
            {
                "columns": ["name", "age"],
                "column_types": ["STRING", "INT64"],
                "rows": [["Alice", 30], ["Bob", 25]],
                "row_count": 2,
                "execution_time_ms": 5,
            }
        )

        # Mock polars
        mock_pl = MagicMock()
        mock_df = MagicMock()
        mock_pl.DataFrame.return_value = mock_df

        with patch.dict("sys.modules", {"polars": mock_pl}):
            df = result.to_polars()

            assert df is mock_df
            mock_pl.DataFrame.assert_called_once()
            # Check that the data was passed correctly
            call_args = mock_pl.DataFrame.call_args[0][0]
            assert call_args == {
                "name": ["Alice", "Bob"],
                "age": [30, 25],
            }

    def test_to_polars_missing_import(self):
        """Test that ImportError is raised when polars not installed."""
        result = QueryResult.from_api_response(
            {
                "columns": ["name"],
                "column_types": ["STRING"],
                "rows": [["Alice"]],
                "row_count": 1,
                "execution_time_ms": 5,
            }
        )

        with patch("builtins.__import__", side_effect=ImportError):
            with pytest.raises(ImportError, match="polars is required"):
                result.to_polars()


class TestQueryResultToPandas:
    """Tests for to_pandas() conversion."""

    def test_to_pandas_success(self):
        """Test converting to Pandas DataFrame."""
        result = QueryResult.from_api_response(
            {
                "columns": ["name", "age"],
                "column_types": ["STRING", "INT64"],
                "rows": [["Alice", 30], ["Bob", 25]],
                "row_count": 2,
                "execution_time_ms": 5,
            }
        )

        # Mock pandas
        mock_pd = MagicMock()
        mock_df = MagicMock()
        mock_pd.DataFrame.return_value = mock_df

        with patch.dict("sys.modules", {"pandas": mock_pd}):
            df = result.to_pandas()

            assert df is mock_df
            mock_pd.DataFrame.assert_called_once_with(
                [["Alice", 30], ["Bob", 25]], columns=["name", "age"]
            )

    def test_to_pandas_missing_import(self):
        """Test that ImportError is raised when pandas not installed."""
        result = QueryResult.from_api_response(
            {
                "columns": ["name"],
                "column_types": ["STRING"],
                "rows": [["Alice"]],
                "row_count": 1,
                "execution_time_ms": 5,
            }
        )

        with patch("builtins.__import__", side_effect=ImportError):
            with pytest.raises(ImportError, match="pandas is required"):
                result.to_pandas()


class TestQueryResultToNetworkX:
    """Tests for to_networkx() conversion."""

    def test_to_networkx_with_nodes(self):
        """Test converting graph data to NetworkX."""
        result = QueryResult.from_api_response(
            {
                "columns": ["node"],
                "column_types": ["NODE"],
                "rows": [
                    [{"_id": 1, "_label": "Person", "name": "Alice"}],
                    [{"_id": 2, "_label": "Person", "name": "Bob"}],
                ],
                "row_count": 2,
                "execution_time_ms": 5,
            }
        )

        # Mock networkx
        mock_nx = MagicMock()
        mock_graph = MagicMock()
        mock_nx.DiGraph.return_value = mock_graph

        with patch.dict("sys.modules", {"networkx": mock_nx}):
            g = result.to_networkx()

            assert g is mock_graph
            # Should add nodes with properties
            assert mock_graph.add_node.call_count == 2

    def test_to_networkx_with_edges(self):
        """Test converting edge data to NetworkX."""
        result = QueryResult.from_api_response(
            {
                "columns": ["edge"],
                "column_types": ["EDGE"],
                "rows": [
                    [{"_src": 1, "_dst": 2, "_type": "KNOWS", "since": 2020}],
                ],
                "row_count": 1,
                "execution_time_ms": 5,
            }
        )

        # Mock networkx
        mock_nx = MagicMock()
        mock_graph = MagicMock()
        mock_nx.DiGraph.return_value = mock_graph

        with patch.dict("sys.modules", {"networkx": mock_nx}):
            g = result.to_networkx()

            assert g is mock_graph
            # Should add edge
            mock_graph.add_edge.assert_called_once()

    def test_to_networkx_missing_import(self):
        """Test that ImportError is raised when networkx not installed."""
        result = QueryResult.from_api_response(
            {
                "columns": ["node"],
                "column_types": ["NODE"],
                "rows": [[{"_id": 1, "_label": "Person"}]],
                "row_count": 1,
                "execution_time_ms": 5,
            }
        )

        with patch("builtins.__import__", side_effect=ImportError):
            with pytest.raises(ImportError, match="networkx is required"):
                result.to_networkx()


class TestQueryResultToCsv:
    """Tests for to_csv() export."""

    def test_to_csv_calls_polars(self):
        """Test that to_csv uses polars under the hood."""
        result = QueryResult.from_api_response(
            {
                "columns": ["name"],
                "column_types": ["STRING"],
                "rows": [["Alice"]],
                "row_count": 1,
                "execution_time_ms": 5,
            }
        )

        # Mock polars
        mock_pl = MagicMock()
        mock_df = MagicMock()
        mock_pl.DataFrame.return_value = mock_df

        with patch.dict("sys.modules", {"polars": mock_pl}):
            result.to_csv("/tmp/test.csv")

            mock_df.write_csv.assert_called_once_with("/tmp/test.csv")


class TestQueryResultToParquet:
    """Tests for to_parquet() export."""

    def test_to_parquet_calls_polars(self):
        """Test that to_parquet uses polars under the hood."""
        result = QueryResult.from_api_response(
            {
                "columns": ["name"],
                "column_types": ["STRING"],
                "rows": [["Alice"]],
                "row_count": 1,
                "execution_time_ms": 5,
            }
        )

        # Mock polars
        mock_pl = MagicMock()
        mock_df = MagicMock()
        mock_pl.DataFrame.return_value = mock_df

        with patch.dict("sys.modules", {"polars": mock_pl}):
            result.to_parquet("/tmp/test.parquet")

            mock_df.write_parquet.assert_called_once_with("/tmp/test.parquet")


class TestQueryResultShow:
    """Tests for show() visualization."""

    def test_show_with_tabular_data(self):
        """Test show() with tabular data uses table display."""
        result = QueryResult.from_api_response(
            {
                "columns": ["name", "age"],
                "column_types": ["STRING", "INT64"],
                "rows": [["Alice", 30]],
                "row_count": 1,
                "execution_time_ms": 5,
            }
        )

        # Mock IPython and itables
        mock_display = MagicMock()
        mock_ipython = MagicMock()
        mock_ipython.display = mock_display
        mock_itables = MagicMock()
        mock_pd = MagicMock()

        with patch.dict(
            "sys.modules",
            {"IPython.display": mock_ipython, "itables": mock_itables, "pandas": mock_pd},
        ):
            # This should work without error
            result.show()

    def test_show_with_graph_data(self):
        """Test show() with graph data uses graph visualization."""
        result = QueryResult.from_api_response(
            {
                "columns": ["node"],
                "column_types": ["NODE"],
                "rows": [[{"_id": 1, "_label": "Person"}]],
                "row_count": 1,
                "execution_time_ms": 5,
            }
        )

        # Mock IPython, networkx, and pyvis
        mock_display = MagicMock()
        mock_ipython = MagicMock()
        mock_ipython.display = mock_display
        mock_nx = MagicMock()
        mock_graph = MagicMock()
        mock_nx.DiGraph.return_value = mock_graph
        mock_network = MagicMock()
        mock_pyvis = MagicMock()
        mock_pyvis.network.Network.return_value = mock_network

        with patch.dict(
            "sys.modules",
            {"IPython.display": mock_ipython, "networkx": mock_nx, "pyvis.network": mock_pyvis},
        ):
            # This should work without error
            result.show()

    def test_show_without_ipython_prints(self, capsys):
        """Test show() without IPython falls back to print."""
        result = QueryResult.from_api_response(
            {
                "columns": ["name"],
                "column_types": ["STRING"],
                "rows": [["Alice"]],
                "row_count": 1,
                "execution_time_ms": 5,
            }
        )

        with patch("builtins.__import__", side_effect=ImportError):
            result.show()
            captured = capsys.readouterr()
            # Should print the table
            assert "name" in captured.out


class TestQueryResultShowTable:
    """Tests for _show_table() method."""

    def test_show_table_with_itables(self):
        """Test _show_table uses itables when available."""
        result = QueryResult.from_api_response(
            {
                "columns": ["name"],
                "column_types": ["STRING"],
                "rows": [["Alice"]],
                "row_count": 1,
                "execution_time_ms": 5,
            }
        )

        mock_show = MagicMock()
        mock_itables = MagicMock()
        mock_itables.show = mock_show
        mock_pd = MagicMock()
        mock_df = MagicMock()
        mock_pd.DataFrame.return_value = mock_df

        with patch.dict("sys.modules", {"itables": mock_itables, "pandas": mock_pd}):
            result._show_table(10)
            mock_show.assert_called_once()

    def test_show_table_without_itables_prints(self, capsys):
        """Test _show_table falls back to print without itables."""
        result = QueryResult.from_api_response(
            {
                "columns": ["name"],
                "column_types": ["STRING"],
                "rows": [["Alice"]],
                "row_count": 1,
                "execution_time_ms": 5,
            }
        )

        with patch("builtins.__import__", side_effect=ImportError):
            result._show_table(10)
            captured = capsys.readouterr()
            assert "name" in captured.out


class TestQueryResultShowGraph:
    """Tests for _show_graph() method."""

    def test_show_graph_with_pyvis(self):
        """Test _show_graph uses pyvis when available."""
        result = QueryResult.from_api_response(
            {
                "columns": ["node"],
                "column_types": ["NODE"],
                "rows": [[{"_id": 1, "_label": "Person"}]],
                "row_count": 1,
                "execution_time_ms": 5,
            }
        )

        mock_network_instance = MagicMock()
        mock_network_class = MagicMock(return_value=mock_network_instance)
        mock_pyvis_network = MagicMock()
        mock_pyvis_network.Network = mock_network_class
        mock_nx = MagicMock()
        mock_graph = MagicMock()
        mock_nx.DiGraph.return_value = mock_graph

        with patch.dict(
            "sys.modules", {"pyvis.network": mock_pyvis_network, "networkx": mock_nx}
        ):
            result._show_graph(10)
            mock_network_instance.from_nx.assert_called_once()
            mock_network_instance.show.assert_called_once_with("graph.html")

    def test_show_graph_without_pyvis_prints(self, capsys):
        """Test _show_graph falls back to print without pyvis."""
        result = QueryResult.from_api_response(
            {
                "columns": ["node"],
                "column_types": ["NODE"],
                "rows": [[{"_id": 1, "_label": "Person"}]],
                "row_count": 1,
                "execution_time_ms": 5,
            }
        )

        with patch("builtins.__import__", side_effect=ImportError):
            result._show_graph(10)
            captured = capsys.readouterr()
            # Should fall back to printing
            assert "node" in captured.out


class TestQueryResultPrintTable:
    """Tests for _print_table() method."""

    def test_print_table_basic(self, capsys):
        """Test _print_table outputs correctly."""
        result = QueryResult.from_api_response(
            {
                "columns": ["name", "age"],
                "column_types": ["STRING", "INT64"],
                "rows": [["Alice", 30], ["Bob", 25]],
                "row_count": 2,
                "execution_time_ms": 5,
            }
        )

        result._print_table(10)
        captured = capsys.readouterr()

        assert "name" in captured.out
        assert "age" in captured.out
        assert "Alice" in captured.out
        assert "Bob" in captured.out

    def test_print_table_with_truncation(self, capsys):
        """Test _print_table truncates for large results."""
        result = QueryResult.from_api_response(
            {
                "columns": ["n"],
                "column_types": ["INT64"],
                "rows": [[i] for i in range(100)],
                "row_count": 100,
                "execution_time_ms": 5,
            }
        )

        result._print_table(10)
        captured = capsys.readouterr()

        assert "... and 90 more rows" in captured.out


class TestQueryResultReprHtml:
    """Tests for _repr_html_() method."""

    def test_repr_html_basic(self):
        """Test _repr_html_() generates HTML."""
        result = QueryResult.from_api_response(
            {
                "columns": ["name", "age"],
                "column_types": ["STRING", "INT64"],
                "rows": [["Alice", 30], ["Bob", 25]],
                "row_count": 2,
                "execution_time_ms": 5,
            }
        )

        html = result._repr_html_()

        assert "<table" in html
        assert "name" in html
        assert "age" in html
        assert "Alice" in html
        assert "Bob" in html
        assert "2 rows" in html
        assert "5ms" in html

    def test_repr_html_truncates_large_results(self):
        """Test _repr_html_() truncates large results."""
        result = QueryResult.from_api_response(
            {
                "columns": ["n"],
                "column_types": ["INT64"],
                "rows": [[i] for i in range(100)],
                "row_count": 100,
                "execution_time_ms": 10,
            }
        )

        html = result._repr_html_()

        assert "... and 90 more rows" in html
        assert "100 rows" in html
