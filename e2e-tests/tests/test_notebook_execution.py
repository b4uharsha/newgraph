"""E2E tests that execute Jupyter notebooks.

Auto-discovers notebooks from notebooks.yaml. Adding a test = adding a YAML entry.

Test Coverage:
- SDK notebook execution in actual Jupyter kernel
- All SDK features work end-to-end through notebook interface
- Validates user workflow as documented

Parallel Execution:
Tests are organized into xdist groups defined in notebooks.yaml.
Run modes:
  Sequential:  pytest tests/test_notebook_execution.py
  Parallel:    pytest tests/test_notebook_execution.py -n auto --dist=loadgroup

Error Reporting (ADR-117):
- ALL errors written to stderr via logging.error() — never buffered by xdist
- Full cell source + traceback printed IMMEDIATELY on failure
- Progress logging shows which notebook is running and how long it took

Cleanup Strategy (Google Best Practice):
- The test runner (not notebooks) guarantees cleanup via try/finally blocks
- Cleanup happens even if notebooks fail mid-execution
- Each test cleans up its own resources immediately after execution
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
import time
from collections.abc import Generator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import yaml

from conftest import get_control_plane_url

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration Loading
# =============================================================================


def _load_notebook_config() -> dict[str, Any]:
    """Load notebook configuration from YAML."""
    config_path = Path(__file__).parent.parent / "notebooks.yaml"
    with open(config_path) as f:
        return yaml.safe_load(f)


def _get_notebook_path(name: str) -> Path:
    """Get path to a notebook file."""
    tests_dir = Path(__file__).parent
    notebooks_dir = tests_dir.parent / "notebooks"

    # Support both with and without .ipynb extension
    notebook_name = name if name.endswith(".ipynb") else f"{name}.ipynb"

    # E2E test notebooks are in platform-tests/
    platform_tests_path = notebooks_dir / "platform-tests" / notebook_name
    if platform_tests_path.exists():
        return platform_tests_path

    # Legacy: check root notebooks dir (for backwards compatibility)
    notebook_path = notebooks_dir / notebook_name
    if notebook_path.exists():
        return notebook_path

    # Container fallback (also updated for new structure)
    for container_dir in [
        Path("/app/notebooks/platform-tests"),
        Path("/app/notebooks"),
    ]:
        container_path = container_dir / notebook_name
        if container_path.exists():
            return container_path

    raise FileNotFoundError(f"Notebook not found: {notebook_name}")


# =============================================================================
# Resource Cleanup
# =============================================================================


# =============================================================================
# Notebook Execution
# =============================================================================


def _emit_error(msg: str) -> None:
    """Write error message to stderr AND logging.error().

    ADR-117: stderr is NEVER buffered by pytest-xdist, so errors appear
    immediately in the terminal regardless of parallelism mode.
    """
    # logging.error() goes to stderr via the log handler
    logger.error(msg)
    # Also write directly to stderr in case log handler is misconfigured
    print(msg, file=sys.stderr, flush=True)


def _execute_notebook(
    notebook_name: str,
    output_dir: Path,
    parameters: dict[str, Any],
    test_name: str,
    test_prefix: str | None = None,
    execution_timeout: int = 60,
) -> None:
    """Execute a notebook with papermill and FAIL HARD on any error.

    Google TAP Best Practice: Tests must fail fast and loud.
    - Any cell exception = test failure (reported IMMEDIATELY to stderr)
    - Any unexpected error = test failure
    - No silent failures or ignored errors

    ADR-117: All error output goes to stderr via _emit_error() so it is
    never buffered by pytest-xdist.

    Args:
        notebook_name: Name of the notebook file
        output_dir: Directory for output notebooks
        parameters: Parameters to inject into notebook
        test_name: Human-readable test name for logging
        test_prefix: Resource prefix for cleanup (e.g., "CrudTest")
        execution_timeout: Timeout per cell in seconds (default 60, ADR-117)

    Raises:
        pytest.fail: On ANY error - notebook cell failure, kernel error, timeout, etc.
    """
    import papermill as pm

    notebook_path = _get_notebook_path(notebook_name)
    output_path = output_dir / notebook_name.replace(".ipynb", "_output.ipynb")

    start_time = time.monotonic()
    _emit_error(f"\n>>> RUNNING: {test_name} (cell timeout={execution_timeout}s)")

    test_failed = False
    failure_message = ""

    try:
        pm.execute_notebook(
            str(notebook_path),
            str(output_path),
            parameters=parameters,
            kernel_name="python3",
            progress_bar=False,
            execution_timeout=execution_timeout,
        )
        elapsed = time.monotonic() - start_time
        _emit_error(f">>> PASSED: {test_name} ({elapsed:.1f}s)")

    except pm.PapermillExecutionError as e:
        test_failed = True
        elapsed = time.monotonic() - start_time
        separator = "=" * 70
        error_block = "\n".join([
            "",
            separator,
            f"  CELL FAILURE: {test_name} ({elapsed:.1f}s)",
            separator,
            f"  Cell index: {e.cell_index}",
            f"  Error:      {e.ename}: {e.evalue}",
            "",
            "  --- Cell Source ---",
            str(e.source),
            "",
            "  --- Traceback ---",
            "".join(e.traceback) if e.traceback else "(no traceback)",
            "",
            f"  Output notebook: {output_path}",
            separator,
        ])
        _emit_error(error_block)
        failure_message = f"{test_name} failed at cell {e.cell_index}: {e.ename}: {e.evalue}"

    except Exception as e:
        test_failed = True
        elapsed = time.monotonic() - start_time
        import traceback
        separator = "=" * 70
        error_block = "\n".join([
            "",
            separator,
            f"  UNEXPECTED FAILURE: {test_name} ({elapsed:.1f}s)",
            separator,
            f"  Exception: {type(e).__name__}: {e}",
            "",
            "  --- Full Traceback ---",
            traceback.format_exc(),
            "",
            f"  Output notebook: {output_path}" if output_path.exists() else "",
            separator,
        ])
        _emit_error(error_block)
        failure_message = f"{test_name} failed with unexpected error: {type(e).__name__}: {e}"

    finally:
        # Per-notebook resource cleanup (ADR-122 / cleanup strategy)
        # Terminates instances and deletes mappings created by this notebook,
        # identified by the notebook's prefix from notebooks.yaml.
        # Instance termination cascade-deletes snapshots.
        # Safe for parallel execution: prefix is unique per notebook type,
        # and never matches pool instances (gw*-Pool*) or tutorial-instance.
        if test_prefix:
            try:
                from graph_olap import GraphOLAPClient

                api_url = os.environ.get("GRAPH_OLAP_API_URL", "")
                if api_url:
                    cleanup_client = GraphOLAPClient(
                        api_url=api_url,
                        username=os.environ.get("GRAPH_OLAP_USERNAME", "analyst_alice@e2e.local"),
                        use_case_id=os.environ.get("GRAPH_OLAP_USE_CASE_ID"),
                    )
                    # Terminate instances matching this notebook's prefix
                    try:
                        instances = cleanup_client.instances.list(search=test_prefix, limit=100)
                        for inst in instances.items:
                            if inst.name and inst.name.startswith(f"{test_prefix}-"):
                                try:
                                    cleanup_client.instances.terminate(inst.id)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    # Delete mappings matching this notebook's prefix
                    # (succeeds now because snapshots were cascade-deleted with instances)
                    try:
                        mappings = cleanup_client.mappings.list(search=test_prefix, limit=100)
                        for m in mappings:
                            if hasattr(m, 'name') and m.name and m.name.startswith(f"{test_prefix}-"):
                                try:
                                    cleanup_client.mappings.delete(m.id)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    cleanup_client.close()
            except Exception:
                pass  # Cleanup is best-effort; never block test result

        if test_failed:
            pytest.fail(failure_message)


# =============================================================================
# Parameter Resolution
# =============================================================================


def _resolve_parameters(
    params: dict[str, Any],
    fixtures: dict[str, Any],
) -> dict[str, Any]:
    """Resolve {{fixture.field}} placeholders in parameters.

    Supports:
    - {{fixture_name}} - direct fixture value
    - {{fixture_name.field}} - nested field access
    """
    resolved = {}
    for key, value in params.items():
        if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
            ref = value[2:-2]  # Remove {{ and }}
            if "." in ref:
                fixture_name, field = ref.split(".", 1)
                fixture_value = fixtures.get(fixture_name)
                if isinstance(fixture_value, dict):
                    resolved[key] = fixture_value.get(field)
                else:
                    resolved[key] = None
            else:
                resolved[key] = fixtures.get(ref)
        else:
            resolved[key] = value
    return resolved


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture(scope="module")
def papermill_available() -> bool:
    """Check if papermill is available."""
    try:
        import papermill  # noqa: F401
        return True
    except ImportError:
        return False


@pytest.fixture(scope="module")
def notebook_output_dir() -> Generator[Path, None, None]:
    """Create temporary directory for notebook outputs."""
    output_dir = Path(tempfile.mkdtemp(prefix="notebook_test_"))
    yield output_dir
    shutil.rmtree(output_dir, ignore_errors=True)


@pytest.fixture(scope="session")
def control_plane_url() -> str:
    """Get Control Plane URL for notebook tests."""
    return get_control_plane_url()


# seeded_ids fixture is defined in conftest.py - uses shared_snapshot and
# shared_readonly_instance to provide REAL IDs instead of hardcoded placeholders.


# =============================================================================
# Test Generation
# =============================================================================


def pytest_generate_tests(metafunc):
    """Dynamically generate test cases from notebooks.yaml."""
    if "notebook_config" not in metafunc.fixturenames:
        return

    config = _load_notebook_config()
    defaults = config.get("defaults", {})
    notebooks = config.get("notebooks", {})

    test_cases = []
    ids = []

    for name, nb_config in notebooks.items():
        nb_config = nb_config or {}

        # Merge default parameters with notebook-specific parameters
        default_params = defaults.get("parameters", {}).copy()
        nb_params = nb_config.get("parameters", {})
        merged_params = {**default_params, **nb_params}

        test_cases.append({
            "name": name,
            "xdist_group": nb_config.get("xdist_group", defaults.get("xdist_group", "default")),
            "timeout": nb_config.get("timeout", defaults.get("timeout", 120)),
            "prefix": nb_config.get("prefix"),
            "fixtures": nb_config.get("fixtures", []),
            "parameters": merged_params,
            "skip_if_missing": nb_config.get("skip_if_missing"),
        })
        ids.append(f"test_{name}")

    metafunc.parametrize("notebook_config", test_cases, ids=ids)


# =============================================================================
# Single Parametrized Test
# =============================================================================


@pytest.mark.e2e
def test_notebook(
    notebook_config: dict,
    papermill_available: bool,
    notebook_output_dir: Path,
    control_plane_url: str,
    request: pytest.FixtureRequest,
) -> None:
    """Execute a notebook test.

    This single function replaces all hardcoded test functions.
    Configuration comes from notebooks.yaml.
    """
    if not papermill_available:
        pytest.skip("papermill not installed")

    # Check skip condition
    skip_env = notebook_config.get("skip_if_missing")
    if skip_env and not os.environ.get(skip_env):
        pytest.skip(f"{skip_env} not set")

    # Dynamically request fixtures based on notebook config
    required_fixtures = notebook_config.get("fixtures", [])
    fixture_values = {}
    for fixture_name in required_fixtures:
        try:
            fixture_values[fixture_name] = request.getfixturevalue(fixture_name)
        except pytest.FixtureLookupError:
            pytest.fail(f"Unknown fixture: {fixture_name}")

    # Build fixture dict for parameter resolution
    fixtures = {
        "control_plane_url": control_plane_url,
        "seeded_ids": fixture_values.get("seeded_ids", {}),
        "seeded_mapping_id": fixture_values.get("seeded_mapping_id", {}),
        "shared_readonly_instance": fixture_values.get("shared_readonly_instance"),
        "instance_pool": fixture_values.get("instance_pool", {}),
    }

    # Resolve parameters
    parameters = _resolve_parameters(notebook_config["parameters"], fixtures)

    # Cell timeout = notebook timeout. Notebooks with multiple create_and_wait calls
    # in a single cell need the full timeout. The notebook-level pytest-timeout is the
    # safety net; the cell timeout should not be the bottleneck.
    total_timeout = notebook_config.get("timeout", 180)
    cell_timeout = total_timeout

    # Execute
    _execute_notebook(
        f"{notebook_config['name']}.ipynb",
        notebook_output_dir,
        parameters=parameters,
        test_name=notebook_config["name"],
        test_prefix=notebook_config.get("prefix"),
        execution_timeout=cell_timeout,
    )
