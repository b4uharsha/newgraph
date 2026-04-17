#!/usr/bin/env python3
"""E2E Test Timing Analysis Script

Runs all E2E tests and captures detailed timing data:
- Notebook-level execution time
- Cell-level execution time
- Test-by-test breakdown

Outputs:
- CSV file with timing data (progressive write)
- JSON file with detailed breakdown
- Markdown report with analysis
"""

import csv
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


class TimingAnalyzer:
    """Analyzes E2E test timing data."""

    def __init__(self, output_dir: Path):
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Output files
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.csv_file = self.output_dir / f"timing_data_{timestamp}.csv"
        self.json_file = self.output_dir / f"timing_data_{timestamp}.json"
        self.report_file = self.output_dir / f"timing_report_{timestamp}.md"

        # Data storage
        self.timing_data = []
        self.notebook_timings = {}

        # Initialize CSV
        self._init_csv()

    def _init_csv(self):
        """Initialize CSV file with headers."""
        with open(self.csv_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                'notebook_name',
                'test_order',
                'xdist_group',
                'cell_number',
                'cell_type',
                'cell_execution_time_ms',
                'notebook_total_time_sec',
                'timestamp'
            ])
        print(f"✓ Initialized CSV output: {self.csv_file}")

    def run_tests_with_timing(self):
        """Run all E2E tests and capture timing data."""
        print("\n" + "="*80)
        print("E2E TEST TIMING ANALYSIS - STARTING")
        print("="*80)
        print(f"\nTimestamp: {datetime.now().isoformat()}")
        print(f"Output directory: {self.output_dir}")
        print("\nRunning all E2E notebook tests...")
        print("="*80 + "\n")

        # Run pytest with timing and verbose output
        start_time = time.time()

        cmd = [
            'pytest',
            'tests/e2e/tests/test_notebook_execution.py',
            '-v',
            '--tb=short',
            '--durations=0',  # Show all test durations
            '-k', 'test_sdk',  # Only notebook tests
            '--capture=no',  # Show output in real-time
        ]

        print(f"Command: {' '.join(cmd)}\n")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=Path(__file__).parent.parent.parent.parent,  # repo root
            )

            total_time = time.time() - start_time

            print(result.stdout)
            if result.stderr:
                print("STDERR:", result.stderr, file=sys.stderr)

            # Parse pytest timing output
            self._parse_pytest_output(result.stdout)

            print(f"\n✓ All tests completed in {total_time:.2f}s")
            print(f"  Test result: {'PASSED' if result.returncode == 0 else 'FAILED'}")

            return result.returncode == 0

        except Exception as e:
            print(f"\n✗ Error running tests: {e}", file=sys.stderr)
            return False

    def _parse_pytest_output(self, output: str):
        """Parse pytest output to extract test timing."""
        print("\n" + "="*80)
        print("PARSING PYTEST OUTPUT FOR TIMING DATA")
        print("="*80 + "\n")

        # Parse test durations from pytest --durations output
        # Format: "0.95s call     tests/e2e/tests/test_notebook_execution.py::test_sdk_smoke_notebook"
        duration_pattern = re.compile(r'([\d.]+)s\s+call\s+.*::test_sdk_(\w+)_notebook')

        for line in output.split('\n'):
            match = duration_pattern.search(line)
            if match:
                duration = float(match.group(1))
                notebook_name = f"sdk_{match.group(2)}_test"

                self.notebook_timings[notebook_name] = {
                    'duration_sec': duration,
                    'notebook_name': notebook_name,
                }

                print(f"  {notebook_name}: {duration:.2f}s")

        print(f"\n✓ Extracted timing for {len(self.notebook_timings)} notebooks")

    def parse_output_notebooks(self, notebook_output_dir: Path):
        """Parse papermill output notebooks to extract cell-level timing."""
        print("\n" + "="*80)
        print("PARSING OUTPUT NOTEBOOKS FOR CELL-LEVEL TIMING")
        print("="*80 + "\n")

        if not notebook_output_dir.exists():
            print(f"⚠️  Output directory not found: {notebook_output_dir}")
            print("   Cell-level timing will not be available.")
            return

        output_notebooks = list(notebook_output_dir.glob("*_output.ipynb"))
        print(f"Found {len(output_notebooks)} output notebooks\n")

        for nb_path in sorted(output_notebooks):
            self._parse_notebook_timing(nb_path)

    def _parse_notebook_timing(self, nb_path: Path):
        """Parse a single output notebook for timing data."""
        try:
            with open(nb_path) as f:
                nb_data = json.load(f)

            # Extract notebook name from filename
            # Format: sdk_crud_test_output.ipynb -> sdk_crud_test
            notebook_name = nb_path.stem.replace('_output', '')

            print(f"Parsing: {notebook_name}")

            # Get notebook-level timing from our previous parse
            notebook_timing = self.notebook_timings.get(notebook_name, {})
            total_time_sec = notebook_timing.get('duration_sec', 0)

            # Extract metadata for test order and group
            metadata = nb_data.get('metadata', {})
            test_order = self._extract_test_order(notebook_name)
            xdist_group = self._extract_xdist_group(notebook_name)

            # Parse cells for timing
            cells = nb_data.get('cells', [])
            total_cell_time_ms = 0

            for cell_num, cell in enumerate(cells, start=1):
                cell_type = cell.get('cell_type', 'unknown')

                # Papermill adds execution metadata
                metadata = cell.get('metadata', {})
                execution = metadata.get('execution', {})

                # Calculate cell execution time
                start_time = execution.get('iopub.execute_input')
                end_time = execution.get('shell.execute_reply')

                cell_time_ms = 0
                if start_time and end_time:
                    # Parse ISO timestamps
                    start_dt = datetime.fromisoformat(start_time.replace('Z', '+00:00'))
                    end_dt = datetime.fromisoformat(end_time.replace('Z', '+00:00'))
                    cell_time_ms = (end_dt - start_dt).total_seconds() * 1000
                    total_cell_time_ms += cell_time_ms

                # Record cell timing
                row_data = {
                    'notebook_name': notebook_name,
                    'test_order': test_order,
                    'xdist_group': xdist_group,
                    'cell_number': cell_num,
                    'cell_type': cell_type,
                    'cell_execution_time_ms': round(cell_time_ms, 2),
                    'notebook_total_time_sec': round(total_time_sec, 2),
                    'timestamp': datetime.now().isoformat(),
                }

                self.timing_data.append(row_data)

                # Write to CSV progressively
                self._append_to_csv(row_data)

            print(f"  ✓ {len(cells)} cells, total cell time: {total_cell_time_ms/1000:.2f}s")
            print(f"    (notebook reported time: {total_time_sec:.2f}s)\n")

        except Exception as e:
            print(f"  ✗ Error parsing {nb_path.name}: {e}\n")

    def _extract_test_order(self, notebook_name: str) -> int:
        """Extract test order from notebook name."""
        # Map from test_notebook_execution.py
        order_map = {
            'sdk_smoke_test': 1,
            'sdk_crud_test': 2,
            'sdk_query_test': 3,
            'sdk_algorithm_test': 4,
            'sdk_authorization_test': 5,
            'sdk_ops_test': 6,
            'sdk_validation_test': 7,
            'sdk_workflow_test': 8,
            'sdk_export_test': 9,
            'sdk_background_jobs_test': 10,
            'sdk_admin_test': 11,
            'sdk_schema_test': 12,
        }
        return order_map.get(notebook_name, 999)

    def _extract_xdist_group(self, notebook_name: str) -> str:
        """Extract xdist group from notebook name."""
        # Map from test_notebook_execution.py
        group_map = {
            'sdk_smoke_test': 'smoke',
            'sdk_crud_test': 'crud',
            'sdk_query_test': 'query',
            'sdk_algorithm_test': 'instance_lock',
            'sdk_authorization_test': 'global_state',
            'sdk_ops_test': 'global_state',
            'sdk_validation_test': 'validation',
            'sdk_workflow_test': 'instance_lock',
            'sdk_export_test': 'export',
            'sdk_background_jobs_test': 'global_state',
            'sdk_admin_test': 'global_state',
            'sdk_schema_test': 'query',
        }
        return group_map.get(notebook_name, 'unknown')

    def _append_to_csv(self, row_data: dict[str, Any]):
        """Append a row to the CSV file."""
        with open(self.csv_file, 'a', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                row_data['notebook_name'],
                row_data['test_order'],
                row_data['xdist_group'],
                row_data['cell_number'],
                row_data['cell_type'],
                row_data['cell_execution_time_ms'],
                row_data['notebook_total_time_sec'],
                row_data['timestamp'],
            ])

    def save_json_data(self):
        """Save complete timing data to JSON."""
        print("\n" + "="*80)
        print("SAVING JSON DATA")
        print("="*80 + "\n")

        output = {
            'metadata': {
                'timestamp': datetime.now().isoformat(),
                'total_notebooks': len(self.notebook_timings),
                'total_cells': len(self.timing_data),
            },
            'notebook_timings': self.notebook_timings,
            'cell_timings': self.timing_data,
        }

        with open(self.json_file, 'w') as f:
            json.dump(output, f, indent=2)

        print(f"✓ Saved JSON data: {self.json_file}")

    def generate_report(self):
        """Generate markdown timing report with analysis."""
        print("\n" + "="*80)
        print("GENERATING TIMING REPORT")
        print("="*80 + "\n")

        # Calculate statistics
        notebook_times = [nb['duration_sec'] for nb in self.notebook_timings.values()]
        total_time = sum(notebook_times)

        # Group by xdist_group
        group_times = {}
        for nb_name, nb_data in self.notebook_timings.items():
            group = self._extract_xdist_group(nb_name)
            if group not in group_times:
                group_times[group] = []
            group_times[group].append(nb_data['duration_sec'])

        # Generate report
        report = []
        report.append("# E2E Test Timing Analysis Report")
        report.append("")
        report.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report.append(f"**Total Notebooks:** {len(self.notebook_timings)}")
        report.append(f"**Total Execution Time:** {total_time:.2f}s ({total_time/60:.2f} minutes)")
        report.append("")
        report.append("---")
        report.append("")

        # Summary statistics
        report.append("## Summary Statistics")
        report.append("")
        if notebook_times:
            report.append(f"- **Fastest notebook:** {min(notebook_times):.2f}s")
            report.append(f"- **Slowest notebook:** {max(notebook_times):.2f}s")
            report.append(f"- **Average notebook time:** {sum(notebook_times)/len(notebook_times):.2f}s")
            report.append(f"- **Median notebook time:** {sorted(notebook_times)[len(notebook_times)//2]:.2f}s")
        report.append("")
        report.append("---")
        report.append("")

        # Timing by xdist group
        report.append("## Timing by xdist Group")
        report.append("")
        report.append("These groups run in parallel with `pytest -n auto --dist=loadgroup`:")
        report.append("")
        report.append("| Group | Notebooks | Total Time | Avg Time | Notes |")
        report.append("|-------|-----------|------------|----------|-------|")

        for group in sorted(group_times.keys()):
            times = group_times[group]
            total = sum(times)
            avg = total / len(times) if times else 0

            # Add notes
            notes = ""
            if group == "smoke":
                notes = "Runs first, validates stack"
            elif group == "instance_lock":
                notes = "Sequential (algorithm lock)"
            elif group == "global_state":
                notes = "Sequential (modifies config)"
            else:
                notes = "Can run in parallel"

            report.append(f"| {group} | {len(times)} | {total:.2f}s | {avg:.2f}s | {notes} |")

        report.append("")
        report.append("---")
        report.append("")

        # Individual notebook timing
        report.append("## Individual Notebook Timing")
        report.append("")
        report.append("| Order | Notebook | Group | Time (s) | % of Total |")
        report.append("|-------|----------|-------|----------|------------|")

        # Sort by test order
        sorted_notebooks = sorted(
            self.notebook_timings.items(),
            key=lambda x: self._extract_test_order(x[0])
        )

        for nb_name, nb_data in sorted_notebooks:
            order = self._extract_test_order(nb_name)
            group = self._extract_xdist_group(nb_name)
            duration = nb_data['duration_sec']
            pct = (duration / total_time * 100) if total_time > 0 else 0

            report.append(f"| {order} | `{nb_name}` | {group} | {duration:.2f} | {pct:.1f}% |")

        report.append("")
        report.append("---")
        report.append("")

        # Optimization opportunities
        report.append("## Optimization Opportunities")
        report.append("")
        report.append("### Slowest Notebooks (Targets for Optimization)")
        report.append("")

        # Top 5 slowest
        top_slowest = sorted(
            sorted_notebooks,
            key=lambda x: x[1]['duration_sec'],
            reverse=True
        )[:5]

        report.append("| Rank | Notebook | Time (s) | Optimization Potential |")
        report.append("|------|----------|----------|------------------------|")

        for rank, (nb_name, nb_data) in enumerate(top_slowest, start=1):
            duration = nb_data['duration_sec']

            # Suggest optimization
            suggestion = ""
            if duration > 60:
                suggestion = "⚠️ Very slow - needs investigation"
            elif duration > 30:
                suggestion = "Consider optimization"
            elif duration > 10:
                suggestion = "Review for quick wins"
            else:
                suggestion = "Already fast"

            report.append(f"| {rank} | `{nb_name}` | {duration:.2f} | {suggestion} |")

        report.append("")
        report.append("### Parallel Execution Potential")
        report.append("")
        report.append("Current sequential groups that could potentially run in parallel:")
        report.append("")

        # Calculate sequential time
        sequential_groups = ['instance_lock', 'global_state']
        sequential_time = sum(sum(group_times.get(g, [])) for g in sequential_groups)

        report.append(f"- **instance_lock group:** {sum(group_times.get('instance_lock', [])):.2f}s")
        report.append(f"- **global_state group:** {sum(group_times.get('global_state', [])):.2f}s")
        report.append(f"- **Total sequential time:** {sequential_time:.2f}s")
        report.append("")
        report.append("If these could run in parallel, potential time savings:")
        report.append(f"- Current: {sequential_time:.2f}s")
        report.append(f"- Parallel: {max(group_times.get('instance_lock', [0]) or [0] + group_times.get('global_state', [0]) or [0]):.2f}s")
        report.append("")

        report.append("---")
        report.append("")

        # Data files
        report.append("## Data Files")
        report.append("")
        report.append(f"- **CSV data:** `{self.csv_file.name}`")
        report.append(f"- **JSON data:** `{self.json_file.name}`")
        report.append("")
        report.append("### CSV Format")
        report.append("")
        report.append("```csv")
        report.append("notebook_name,test_order,xdist_group,cell_number,cell_type,cell_execution_time_ms,notebook_total_time_sec,timestamp")
        report.append("```")
        report.append("")

        # Write report
        with open(self.report_file, 'w') as f:
            f.write('\n'.join(report))

        print(f"✓ Generated timing report: {self.report_file}")

        # Print summary to console
        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)
        print(f"\nTotal execution time: {total_time:.2f}s ({total_time/60:.2f} minutes)")
        print(f"Notebooks tested: {len(self.notebook_timings)}")
        print("\nTop 3 slowest notebooks:")
        for rank, (nb_name, nb_data) in enumerate(top_slowest[:3], start=1):
            print(f"  {rank}. {nb_name}: {nb_data['duration_sec']:.2f}s")
        print(f"\nDetailed report saved to: {self.report_file}")


def main():
    """Main entry point."""
    # Determine output directory
    script_dir = Path(__file__).parent
    output_dir = script_dir.parent / "timing_analysis"

    analyzer = TimingAnalyzer(output_dir)

    # Run tests and capture timing
    success = analyzer.run_tests_with_timing()

    if not success:
        print("\n⚠️  Tests failed, but continuing with timing analysis...")

    # Find notebook output directory
    # Papermill creates output notebooks in a temp directory
    # We need to find it from pytest output or use a known location
    notebook_output_dirs = [
        Path("/tmp").glob("notebook_test_*"),
        script_dir.parent.parent.parent / "notebook_outputs",
    ]

    # Try to find output notebooks
    found_output = False
    for pattern in notebook_output_dirs:
        if isinstance(pattern, Path):
            dirs = [pattern] if pattern.exists() else []
        else:
            dirs = list(pattern)

        for nb_output_dir in dirs:
            if nb_output_dir.exists():
                analyzer.parse_output_notebooks(nb_output_dir)
                found_output = True
                break

        if found_output:
            break

    if not found_output:
        print("\n⚠️  Could not find notebook output directory")
        print("   Cell-level timing data will not be available")
        print("   Only notebook-level timing will be reported")

    # Save data and generate report
    analyzer.save_json_data()
    analyzer.generate_report()

    print("\n" + "="*80)
    print("TIMING ANALYSIS COMPLETE")
    print("="*80)
    print("\nOutput files:")
    print(f"  - CSV: {analyzer.csv_file}")
    print(f"  - JSON: {analyzer.json_file}")
    print(f"  - Report: {analyzer.report_file}")
    print("")


if __name__ == "__main__":
    main()
