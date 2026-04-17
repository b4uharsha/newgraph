---
title: "Python Linting Standards"
scope: hsbc
---

# Python Linting Standards

This document establishes coding standards for linting and static analysis in the Graph OLAP Platform, based on industry best practices for 2024-2025.

## Table of Contents

1. [Tooling Strategy](#tooling-strategy)
2. [Ruff Configuration](#ruff-configuration)
3. [Type Checking with mypy](#type-checking-with-mypy)
4. [Pre-commit Integration](#pre-commit-integration)
5. [CI/CD Integration](#cicd-integration)
6. [Rule Categories](#rule-categories)

## Tooling Strategy

### Primary Tools

| Tool | Purpose | Performance |
|------|---------|-------------|
| **Ruff** | Linting + Formatting | 10-100x faster than alternatives |
| **mypy** | Static type checking | Industry standard |

### Why Ruff?

Ruff has emerged as the industry standard for Python linting in 2024-2025:

- **Speed**: 10-100x faster than Flake8/Pylint (written in Rust)
- **Consolidation**: Replaces Flake8, isort, pyupgrade, autoflake, and 50+ plugins
- **800+ rules**: Comprehensive coverage from multiple linting traditions
- **Built-in formatter**: Can replace Black for code formatting
- **Single configuration**: One tool, one config section in `pyproject.toml`

### Tool Comparison

| Capability | Ruff | Flake8 | Pylint |
|------------|------|--------|--------|
| Speed (relative) | 1x | 10x slower | 100x slower |
| Auto-fix | Yes | No | Limited |
| Import sorting | Yes (isort) | Plugin | No |
| Code upgrade | Yes (pyupgrade) | Plugin | No |
| Configuration | pyproject.toml | Multiple files | Multiple files |

## Ruff Configuration

### Standard Configuration

All packages in this monorepo use a consistent Ruff configuration:

```toml
[tool.ruff]
target-version = "py311"
line-length = 100

[tool.ruff.lint]
select = [
    "E",      # pycodestyle errors
    "W",      # pycodestyle warnings
    "F",      # Pyflakes (undefined names, unused imports)
    "I",      # isort (import ordering)
    "N",      # pep8-naming (naming conventions)
    "UP",     # pyupgrade (modern Python syntax)
    "B",      # flake8-bugbear (common bugs)
    "C4",     # flake8-comprehensions (comprehension best practices)
    "SIM",    # flake8-simplify (code simplification)
    "ARG",    # flake8-unused-arguments
    "PTH",    # flake8-use-pathlib
    "ERA",    # eradicate (commented-out code)
    "RUF",    # Ruff-specific rules
]
ignore = [
    "E501",   # Line too long (handled by formatter)
    "B008",   # Function call in default argument (FastAPI Depends)
    "SIM105", # Use contextlib.suppress (explicit try/except often clearer)
    "SIM117", # Multiple with statements (readability)
]

[tool.ruff.lint.isort]
known-first-party = ["control_plane", "graph_olap", "export_worker", "wrapper", "graph_olap_schemas"]

[tool.ruff.format]
quote-style = "double"
indent-style = "space"
skip-magic-trailing-comma = false
line-ending = "auto"
```

### Package-Specific Overrides

Some packages may have additional rules or ignores based on their needs:

```toml
# For packages with heavy Pydantic usage
[tool.ruff.lint.per-file-ignores]
"*/models/*.py" = ["N815"]  # Allow mixedCase for Pydantic field aliases
"*/tests/*.py" = ["ARG001"]  # Unused arguments common in fixtures
```

### Rule Categories Explained

#### E/W: pycodestyle (PEP 8 Style)

Basic style compliance:

```python
# E101: Indentation contains mixed spaces and tabs
# E302: Expected 2 blank lines, found 1
# W291: Trailing whitespace
# W503: Line break before binary operator
```

#### F: Pyflakes (Logical Errors)

Catch bugs before they happen:

```python
# F401: Module imported but unused
# F811: Redefinition of unused name
# F841: Local variable assigned but never used
# F821: Undefined name
```

#### I: isort (Import Ordering)

Consistent import organization:

```python
# Correct order:
from __future__ import annotations  # 1. Future imports

import os                           # 2. Standard library
import sys
from pathlib import Path

import httpx                        # 3. Third-party
from pydantic import BaseModel

from control_plane.models import User  # 4. First-party
from control_plane.utils import helper
```

#### N: pep8-naming

Naming convention enforcement:

```python
# N801: Class name should use CapWords
# N802: Function name should be lowercase
# N803: Argument name should be lowercase
# N806: Variable in function should be lowercase
```

#### UP: pyupgrade

Modern Python syntax:

```python
# Before (UP006): Use list instead of typing.List
from typing import List
def process(items: List[str]) -> None: ...

# After
def process(items: list[str]) -> None: ...

# Before (UP035): Use dict instead of typing.Dict
from typing import Dict
config: Dict[str, int] = {}

# After
config: dict[str, int] = {}
```

#### B: flake8-bugbear

Catch common bugs:

```python
# B006: Mutable default argument
def bad(items=[]):  # Bug!
    items.append(1)

def good(items=None):
    items = items or []
    items.append(1)

# B007: Loop control variable not used (use _)
for i in range(10):  # i unused
    print("hello")

for _ in range(10):  # Correct
    print("hello")
```

#### C4: flake8-comprehensions

Efficient comprehensions:

```python
# C400: Unnecessary generator, use list comprehension
list(x for x in items)  # Bad
[x for x in items]      # Good

# C401: Unnecessary generator, use set comprehension
set(x for x in items)  # Bad
{x for x in items}     # Good
```

#### SIM: flake8-simplify

Code simplification:

```python
# SIM102: Use single if instead of nested
if a:
    if b:
        do_thing()
# Better:
if a and b:
    do_thing()

# SIM108: Use ternary operator
if condition:
    x = a
else:
    x = b
# Better:
x = a if condition else b
```

#### ARG: flake8-unused-arguments

Detect unused function arguments:

```python
# ARG001: Unused function argument
def process(data, unused_param):  # unused_param never used
    return transform(data)

# Fix: Remove or prefix with underscore
def process(data, _unused_param):
    return transform(data)
```

#### PTH: flake8-use-pathlib

Prefer pathlib over os.path:

```python
# PTH100: Use Path.cwd() instead of os.getcwd()
import os
cwd = os.getcwd()

from pathlib import Path
cwd = Path.cwd()

# PTH118: Use Path(...) / "file" instead of os.path.join
import os
path = os.path.join(dir, "file.txt")

from pathlib import Path
path = Path(dir) / "file.txt"
```

#### ERA: eradicate

Remove commented-out code:

```python
# ERA001: Found commented-out code
# def old_function():
#     return legacy_call()

# Fix: Delete it. Use version control for history.
```

#### RUF: Ruff-specific

Ruff's own rules:

```python
# RUF001: Ambiguous unicode character
text = "foo" # 'o' is Cyrillic

# RUF012: Mutable class attributes should be annotated with ClassVar
class Config:
    items = []  # Should be ClassVar[list]
```

## Type Checking with mypy

### Standard Configuration

```toml
[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_ignores = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
no_implicit_optional = true

# Third-party library handling
ignore_missing_imports = false

[[tool.mypy.overrides]]
module = [
    "kubernetes.*",
    "google.cloud.*",
]
ignore_missing_imports = true

# Pydantic plugin for better validation
plugins = ["pydantic.mypy"]

[tool.pydantic-mypy]
init_forbid_extra = true
init_typed = true
warn_required_dynamic_aliases = true
```

### Type Annotation Standards

```python
# Use modern syntax (Python 3.10+)
def process(items: list[str]) -> dict[str, int]: ...

# Use | for unions instead of Union
def get_value(key: str) -> str | None: ...

# Use lowercase generics
from collections.abc import Sequence, Mapping

def transform(data: Sequence[Mapping[str, int]]) -> list[int]: ...

# Annotate all public APIs
class UserService:
    def get_user(self, user_id: str) -> User: ...
    def list_users(self, limit: int = 100) -> list[User]: ...
```

## Pre-commit Integration

### Configuration

Create `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format

  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.13.0
    hooks:
      - id: mypy
        additional_dependencies:
          - pydantic
          - types-requests
```

### Installation

```bash
# Install pre-commit
pip install pre-commit

# Install hooks
pre-commit install

# Run on all files
pre-commit run --all-files
```

## CI/CD Integration

### Jenkins Pipeline Stage

HSBC CI runs on Jenkins (no GitHub Actions). Add the lint stage to the repository's `Jenkinsfile`:

```groovy
stage('Lint') {
    agent {
        docker { image 'python:3.11' }
    }
    steps {
        sh '''
            pip install ruff mypy
            ruff check .
            ruff format --check .
            mypy .
        '''
    }
}
```

### Make Commands

```makefile
.PHONY: lint format

lint:
	ruff check .

format:
	ruff format .
	ruff check --fix .
```

## Rule Categories

### Enabled by Default

| Category | Purpose | Priority |
|----------|---------|----------|
| E/W | PEP 8 style | High |
| F | Pyflakes errors | Critical |
| I | Import sorting | High |
| N | Naming conventions | Medium |
| UP | Python upgrades | Medium |
| B | Bug detection | Critical |

### Recommended Additions

| Category | Purpose | When to Add |
|----------|---------|-------------|
| C4 | Comprehensions | Always |
| SIM | Simplification | Always |
| ARG | Unused arguments | For APIs |
| PTH | Pathlib usage | For file operations |
| ERA | Dead code | For cleanup |
| RUF | Ruff extras | Always |

### Optional Categories

| Category | Purpose | When to Add |
|----------|---------|-------------|
| S | Security (bandit) | Security-critical code |
| D | Docstrings (pydocstyle) | Public APIs |
| ANN | Type annotations | Strict typing projects |
| T20 | Print statements | Production code |
| LOG | Logging issues | Logging-heavy code |

### Ignoring Rules

When you need to ignore a rule, prefer inline comments:

```python
# For a single line
result = process(data)  # noqa: ARG001

# For a block
# ruff: noqa: E501
long_string = "This is a very long string that exceeds the line length limit but we need it this way"

# For an entire file (at top)
# ruff: noqa: E501, ARG001
```

### Adding Rule Ignore to Config

Only add to config-level ignore for project-wide decisions:

```toml
[tool.ruff.lint]
ignore = [
    "E501",   # Always ignore - handled by formatter
    "B008",   # Project uses FastAPI Depends pattern
]
```

## Migration Checklist

When onboarding a new package:

1. Add Ruff configuration to `pyproject.toml`
2. Run `ruff check . --fix` to auto-fix issues
3. Run `ruff format .` to format code
4. Add mypy configuration
5. Run `mypy .` and fix type errors
6. Set up pre-commit hooks
7. Add to CI/CD pipeline

## References

- [Ruff Documentation](https://docs.astral.sh/ruff/)
- [Ruff Rules Reference](https://docs.astral.sh/ruff/rules/)
- [mypy Documentation](https://mypy.readthedocs.io/)
- [PEP 8 Style Guide](https://peps.python.org/pep-0008/)
- [Google Python Style Guide](https://google.github.io/styleguide/pyguide.html)
