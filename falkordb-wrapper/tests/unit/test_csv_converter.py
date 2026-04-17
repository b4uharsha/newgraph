"""Unit tests for CSV converter utility."""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from wrapper.utils.csv_converter import CSVConverter


class TestCSVConverter:
    """Tests for CSVConverter."""

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_convert_parquet_to_csv_basic(self, tmp_path: Path):
        """Test basic Parquet to CSV conversion."""
        # Create test Parquet
        parquet_path = tmp_path / "test.parquet"
        df = pl.DataFrame({
            "id": [1, 2, 3],
            "name": ["Alice", "Bob", "Charlie"],
            "active": [True, False, True],
        })
        df.write_parquet(parquet_path)

        # Convert
        csv_path = tmp_path / "test.csv"
        row_count = await CSVConverter.convert_parquet_to_csv(parquet_path, csv_path)

        # Verify
        assert row_count == 3
        assert csv_path.exists()
        df_csv = pl.read_csv(csv_path)
        assert df_csv.shape == (3, 3)
        assert list(df_csv.columns) == ["id", "name", "active"]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_convert_handles_missing_file(self, tmp_path: Path):
        """Test error handling for missing Parquet file."""
        parquet_path = tmp_path / "nonexistent.parquet"
        csv_path = tmp_path / "output.csv"

        with pytest.raises(FileNotFoundError, match="Parquet file not found"):
            await CSVConverter.convert_parquet_to_csv(parquet_path, csv_path)

        # Ensure no partial CSV file created
        assert not csv_path.exists()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_convert_handles_null_values(self, tmp_path: Path):
        """Test that null values are handled correctly in CSV output."""
        parquet_path = tmp_path / "nulls.parquet"
        df = pl.DataFrame({
            "id": [1, 2, 3],
            "name": ["Alice", None, "Charlie"],
            "age": [30, None, 25],
        })
        df.write_parquet(parquet_path)

        csv_path = tmp_path / "nulls.csv"
        row_count = await CSVConverter.convert_parquet_to_csv(parquet_path, csv_path)

        assert row_count == 3
        # Read back and verify nulls preserved
        df_csv = pl.read_csv(csv_path)
        assert df_csv["name"][1] is None
        assert df_csv["age"][1] is None

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_convert_handles_special_characters(self, tmp_path: Path):
        """Test that special characters are properly escaped in CSV."""
        parquet_path = tmp_path / "special.parquet"
        df = pl.DataFrame({
            "id": [1, 2, 3],
            "text": [
                'Hello, World',           # comma
                'Say "Hello"',            # quotes
                'Line1\nLine2',           # newline
            ],
        })
        df.write_parquet(parquet_path)

        csv_path = tmp_path / "special.csv"
        row_count = await CSVConverter.convert_parquet_to_csv(parquet_path, csv_path)

        assert row_count == 3
        df_csv = pl.read_csv(csv_path)
        assert df_csv["text"][0] == 'Hello, World'
        assert df_csv["text"][1] == 'Say "Hello"'
        assert df_csv["text"][2] == 'Line1\nLine2'

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_convert_empty_file(self, tmp_path: Path):
        """Test conversion of empty Parquet file."""
        parquet_path = tmp_path / "empty.parquet"
        df = pl.DataFrame({
            "id": pl.Series([], dtype=pl.Int64),
            "name": pl.Series([], dtype=pl.Utf8),
        })
        df.write_parquet(parquet_path)

        csv_path = tmp_path / "empty.csv"
        row_count = await CSVConverter.convert_parquet_to_csv(parquet_path, csv_path)

        assert row_count == 0
        assert csv_path.exists()

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_convert_with_various_types(self, tmp_path: Path):
        """Test conversion with various data types."""
        parquet_path = tmp_path / "types.parquet"
        df = pl.DataFrame({
            "int_col": [1, 2, 3],
            "float_col": [1.1, 2.2, 3.3],
            "str_col": ["a", "b", "c"],
            "bool_col": [True, False, True],
        })
        df.write_parquet(parquet_path)

        csv_path = tmp_path / "types.csv"
        row_count = await CSVConverter.convert_parquet_to_csv(parquet_path, csv_path)

        assert row_count == 3
        df_csv = pl.read_csv(csv_path)
        assert df_csv["int_col"].to_list() == [1, 2, 3]
        assert df_csv["float_col"].to_list() == [1.1, 2.2, 3.3]
        assert df_csv["str_col"].to_list() == ["a", "b", "c"]
        # Polars reads booleans back as actual booleans
        assert df_csv["bool_col"].to_list() == [True, False, True]

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_row_count(self, tmp_path: Path):
        """Test getting row count from Parquet file."""
        parquet_path = tmp_path / "count.parquet"
        df = pl.DataFrame({
            "id": list(range(100)),
            "value": list(range(100)),
        })
        df.write_parquet(parquet_path)

        row_count = await CSVConverter.get_row_count(parquet_path)
        assert row_count == 100

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_get_row_count_missing_file(self, tmp_path: Path):
        """Test error handling for missing file in get_row_count."""
        parquet_path = tmp_path / "nonexistent.parquet"

        with pytest.raises(FileNotFoundError, match="Parquet file not found"):
            await CSVConverter.get_row_count(parquet_path)

    @pytest.mark.asyncio
    @pytest.mark.unit
    async def test_convert_overwrites_existing_csv(self, tmp_path: Path):
        """Test that conversion overwrites existing CSV file."""
        parquet_path = tmp_path / "overwrite.parquet"
        csv_path = tmp_path / "overwrite.csv"

        # Create initial CSV with different content
        csv_path.write_text("old,content\n1,2\n")

        # Create Parquet with new content
        df = pl.DataFrame({
            "id": [10, 20, 30],
            "name": ["X", "Y", "Z"],
        })
        df.write_parquet(parquet_path)

        # Convert should overwrite
        row_count = await CSVConverter.convert_parquet_to_csv(parquet_path, csv_path)

        assert row_count == 3
        df_csv = pl.read_csv(csv_path)
        assert list(df_csv.columns) == ["id", "name"]
        assert df_csv["id"].to_list() == [10, 20, 30]
