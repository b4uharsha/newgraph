# export-worker - HSBC Container Build
SHELL := /bin/bash
IMAGE_NAME ?= export-worker
TAG ?= latest
REGISTRY ?= nexus302.systems.uk.hsbc:8082

.PHONY: help install test lint lint-fix build push deploy status logs shell clean

help:
	@echo "$(IMAGE_NAME) - HSBC Graph OLAP Service"
	@echo ""
	@echo "Development:"
	@echo "  make install             Install dependencies locally"
	@echo "  make test                Run tests"
	@echo "  make lint                Run linter"
	@echo "  make lint-fix            Auto-fix lint issues"
	@echo ""
	@echo "Build & Deploy:"
	@echo "  make build [TAG=x]       Build Docker image"
	@echo "  make push [TAG=x]        Push to Nexus registry"
	@echo "  make deploy              Deploy to GKE"
	@echo "  make status              Check deployment"
	@echo ""
	@echo "Operations:"
	@echo "  make logs                Tail service logs"
	@echo "  make shell               Exec into pod"
	@echo "  make clean               Remove artifacts"

install:
	pip install -e ".[dev]"

test:
	@echo "Running tests for $(IMAGE_NAME)..."
	pytest tests/ -v

lint:
	ruff check .
	ruff format --check .

lint-fix:
	ruff check . --fix
	ruff format .

build:
	@echo "Building $(IMAGE_NAME):$(TAG)..."
	docker build \
		--build-arg ALM_NEXUS302_TOKEN_USERNAME=$${ALM_NEXUS302_TOKEN_USERNAME} \
		--build-arg ALM_NEXUS302_TOKEN_PASSWORD=$${ALM_NEXUS302_TOKEN_PASSWORD} \
		-t $(REGISTRY)/$(IMAGE_NAME):$(TAG) .

push:
	@echo "Pushing $(IMAGE_NAME):$(TAG)..."
	docker push $(REGISTRY)/$(IMAGE_NAME):$(TAG)

deploy:
	@echo "Deploy via cd/deploy.sh — not per-repo"
	@echo "See ../cd/deploy.sh for deployment orchestration"

status:
	kubectl get pods -n graph-olap-platform -l app=$(IMAGE_NAME)

logs:
	kubectl logs -n graph-olap-platform -l app=$(IMAGE_NAME) -f --tail=100

shell:
	kubectl exec -it -n graph-olap-platform deploy/$(IMAGE_NAME) -- /bin/bash

clean:
	rm -rf dist/ build/ *.egg-info/
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	docker rmi $(REGISTRY)/$(IMAGE_NAME):$(TAG) 2>/dev/null || true
