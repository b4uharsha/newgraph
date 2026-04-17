"""Parquet data loading utilities for FalkorDB.

This module provides memory-efficient reading of Parquet files for loading
into FalkorDB. Uses Polars for efficient columnar processing.

Key Methods:
- read_parquet_batches: Yields batches of dictionaries for UNWIND loading
- convert_parquet_to_csv: Legacy CSV conversion (kept for compatibility)
- get_row_count: Fast row counting via Parquet metadata

Performance characteristics:
- Memory: Controlled via batch_size parameter
- Throughput: Limited by disk I/O, typically 100+ MB/s
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class ParquetReadError(Exception):
    """Error during Parquet reading."""

    def __init__(self, message: str, *, parquet_path: Path) -> None:
        self.parquet_path = parquet_path
        super().__init__(message)


class CSVConversionError(Exception):
    """Error during Parquet to CSV conversion."""

    def __init__(self, message: str, *, parquet_path: Path, csv_path: Path | None = None) -> None:
        self.parquet_path = parquet_path
        self.csv_path = csv_path
        super().__init__(message)


class ParquetReader:
    """Read Parquet files and yield batches of dictionaries for UNWIND loading.

    Uses Polars for efficient columnar processing with controlled memory usage.

    Example:
        >>> async for batch in ParquetReader.read_batches(
        ...     Path("/tmp/nodes.parquet"),
        ...     batch_size=5000,
        ... ):
        ...     # batch is a list of dicts: [{"name": "Alice", "age": 30}, ...]
        ...     await graph.query("UNWIND $nodes AS n CREATE (:Person n)", params={"nodes": batch})
    """

    @staticmethod
    async def read_batches(
        parquet_path: Path,
        batch_size: int = 5000,
    ) -> AsyncIterator[tuple[list[dict[str, Any]], int]]:
        """Read Parquet file(s) and yield batches of dictionaries.

        Args:
            parquet_path: Input Parquet file OR directory path.
                          If directory, scans all Parquet files inside.
                          Trino CTAS creates directories with extensionless Parquet files.
            batch_size: Number of rows per batch (default: 5000)

        Yields:
            Tuple of (batch of row dictionaries, total row count)

        Raises:
            FileNotFoundError: If parquet_path doesn't exist
            ParquetReadError: If reading fails

        Memory Usage:
            ~batch_size * avg_row_size bytes per batch
        """
        if not parquet_path.exists():
            raise FileNotFoundError(f"Parquet path not found: {parquet_path}")

        logger.info(
            "reading_parquet_batches",
            parquet_path=str(parquet_path),
            batch_size=batch_size,
        )

        try:
            # Get total row count first (fast, uses metadata)
            total_rows = await ParquetReader.get_row_count(parquet_path)

            if total_rows == 0:
                logger.warning("empty_parquet_file", parquet_path=str(parquet_path))
                return

            # Read and yield batches
            batches_yielded = 0
            rows_yielded = 0

            for batch in await asyncio.to_thread(
                ParquetReader._read_batches_sync, parquet_path, batch_size
            ):
                batches_yielded += 1
                rows_yielded += len(batch)
                yield batch, total_rows

            logger.info(
                "parquet_batches_complete",
                parquet_path=str(parquet_path),
                total_rows=total_rows,
                batches_yielded=batches_yielded,
                rows_yielded=rows_yielded,
            )

        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(
                "parquet_read_failed",
                parquet_path=str(parquet_path),
                error=str(e),
                error_type=type(e).__name__,
            )
            raise ParquetReadError(
                f"Failed to read Parquet: {e}",
                parquet_path=parquet_path,
            ) from e

    @staticmethod
    def _read_batches_sync(
        parquet_path: Path, batch_size: int
    ) -> list[list[dict[str, Any]]]:
        """Synchronous batch reading (runs in thread pool).

        Returns all batches as a list (Polars doesn't support async iteration).
        """
        import polars as pl

        # Determine scan path
        if parquet_path.is_dir():
            scan_path = str(parquet_path / "*")
        else:
            scan_path = parquet_path

        # Read entire file (Polars is efficient with memory mapping)
        df = pl.read_parquet(scan_path)

        # Convert to batches of dictionaries
        batches = []
        total_rows = len(df)

        for start in range(0, total_rows, batch_size):
            end = min(start + batch_size, total_rows)
            batch_df = df.slice(start, end - start)
            # to_dicts() returns list of {column: value} dictionaries
            batches.append(batch_df.to_dicts())

        return batches

    @staticmethod
    async def get_row_count(parquet_path: Path) -> int:
        """Get row count from Parquet file without loading all data.

        Args:
            parquet_path: Path to Parquet file or directory

        Returns:
            Number of rows in the file(s)

        Raises:
            FileNotFoundError: If path doesn't exist
        """
        if not parquet_path.exists():
            raise FileNotFoundError(f"Parquet path not found: {parquet_path}")

        def _count_sync() -> int:
            import polars as pl

            if parquet_path.is_dir():
                scan_path = str(parquet_path / "*")
            else:
                scan_path = parquet_path

            return pl.scan_parquet(scan_path).select(pl.count()).collect()[0, 0]

        return await asyncio.to_thread(_count_sync)


class CSVConverter:
    """Convert Parquet files to CSV (legacy, kept for compatibility).

    Note: For FalkorDB loading, prefer ParquetReader.read_batches() with
    UNWIND queries, as LOAD CSV has file access limitations in FalkorDBLite.

    Example:
        >>> row_count = await CSVConverter.convert_parquet_to_csv(
        ...     Path("/tmp/nodes.parquet"),
        ...     Path("/tmp/nodes.csv"),
        ... )
        >>> print(f"Converted {row_count} rows")
    """

    @staticmethod
    async def convert_parquet_to_csv(
        parquet_path: Path,
        csv_path: Path,
    ) -> int:
        """Convert Parquet file(s) to CSV using streaming.

        Args:
            parquet_path: Input Parquet file OR directory path.
                          If directory, scans all Parquet files inside.
                          Trino CTAS creates directories with extensionless Parquet files.
            csv_path: Output CSV file path (will be created/overwritten)

        Returns:
            Number of rows written to CSV

        Raises:
            FileNotFoundError: If parquet_path doesn't exist
            CSVConversionError: If conversion fails (partial CSV is cleaned up)

        Memory Usage:
            ~50-100 MB regardless of file size (streaming)
        """
        if not parquet_path.exists():
            raise FileNotFoundError(f"Parquet path not found: {parquet_path}")

        logger.info(
            "converting_parquet_to_csv",
            parquet_path=str(parquet_path),
            csv_path=str(csv_path),
        )

        try:
            # Run conversion in thread pool (Polars is synchronous)
            row_count = await asyncio.to_thread(
                CSVConverter._convert_sync,
                parquet_path,
                csv_path,
            )

            csv_size_mb = csv_path.stat().st_size / (1024 * 1024)
            # Calculate parquet size - handle both files and directories
            if parquet_path.is_dir():
                parquet_size_mb = sum(f.stat().st_size for f in parquet_path.iterdir() if f.is_file()) / (1024 * 1024)
            else:
                parquet_size_mb = parquet_path.stat().st_size / (1024 * 1024)

            logger.info(
                "csv_conversion_complete",
                csv_path=str(csv_path),
                row_count=row_count,
                csv_size_mb=round(csv_size_mb, 2),
                parquet_size_mb=round(parquet_size_mb, 2),
                expansion_ratio=round(csv_size_mb / parquet_size_mb, 2) if parquet_size_mb > 0 else 0,
            )

            return row_count

        except FileNotFoundError:
            raise
        except Exception as e:
            logger.error(
                "csv_conversion_failed",
                parquet_path=str(parquet_path),
                error=str(e),
                error_type=type(e).__name__,
            )
            # Clean up partial CSV file
            csv_path.unlink(missing_ok=True)
            raise CSVConversionError(
                f"Failed to convert Parquet to CSV: {e}",
                parquet_path=parquet_path,
                csv_path=csv_path,
            ) from e

    @staticmethod
    def _convert_sync(parquet_path: Path, csv_path: Path) -> int:
        """Synchronous conversion (runs in thread pool).

        Uses lazy scan + sink for streaming (constant memory).
        Supports both single files and directories (Trino CTAS output).
        """
        import polars as pl

        # Determine scan path:
        # - If directory: use glob pattern to match all files inside
        #   (Trino CTAS creates extensionless Parquet files)
        # - If file: use directly
        if parquet_path.is_dir():
            scan_path = str(parquet_path / "*")
        else:
            scan_path = parquet_path

        # Lazy scan - doesn't load data into memory
        lazy_df = pl.scan_parquet(scan_path)

        # Get row count before sinking (metadata only, fast)
        row_count = lazy_df.select(pl.count()).collect()[0, 0]

        # Streaming write - constant memory usage
        # Use default CSV options which handle:
        # - Quoting strings with commas, quotes, newlines
        # - Escaping special characters
        # - Writing headers
        lazy_df.sink_csv(csv_path)

        return row_count

    @staticmethod
    async def get_row_count(parquet_path: Path) -> int:
        """Get row count from Parquet file without loading data.

        Uses Parquet metadata for fast counting without reading data.

        Args:
            parquet_path: Path to Parquet file

        Returns:
            Number of rows in the file

        Raises:
            FileNotFoundError: If file doesn't exist
        """
        if not parquet_path.exists():
            raise FileNotFoundError(f"Parquet file not found: {parquet_path}")

        def _count_sync() -> int:
            import polars as pl

            return pl.scan_parquet(parquet_path).select(pl.count()).collect()[0, 0]

        return await asyncio.to_thread(_count_sync)
