# graph-olap-sdk - HSBC Python Library
SHELL := /bin/bash
PACKAGE_NAME := graph-olap-sdk
NEXUS_REPO := https://nexus302.systems.uk.hsbc:8081/nexus/repository/pypi-hosted-iHub-dev-n3p/

.PHONY: help install test lint lint-fix build publish clean

help:
	@echo "$(PACKAGE_NAME) - HSBC Graph OLAP Library"
	@echo ""
	@echo "Development:"
	@echo "  make install    Install in editable mode"
	@echo "  make test       Run unit tests"
	@echo "  make lint       Run linter"
	@echo "  make lint-fix   Auto-fix lint issues"
	@echo ""
	@echo "Release:"
	@echo "  make build      Build wheel and sdist"
	@echo "  make publish    Upload to Nexus PyPI"
	@echo "  make clean      Remove build artifacts"

install:
	pip install -e ".[dev]"

test:
	pytest tests/ -v

lint:
	ruff check .
	ruff format --check .

lint-fix:
	ruff check . --fix
	ruff format .

build:
	python -m build

publish: build
	twine upload --repository-url $(NEXUS_REPO) dist/*

clean:
	rm -rf dist/ build/ *.egg-info/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
