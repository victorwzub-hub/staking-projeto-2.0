SHELL := /bin/bash
PYTHON := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: help bootstrap install-backend install-frontend lint typecheck test build e2e e2e-list openapi smoke up down logs migrate clean

help:
	@echo "Targets: bootstrap lint typecheck test build e2e-list openapi smoke up down logs migrate clean"

bootstrap: install-backend install-frontend
	@test -f .env || cp .env.example .env

install-backend:
	python3.12 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -e './apps/api[dev]'
	$(PIP) install -e './apps/worker[dev]'

install-frontend:
	npm ci

lint:
	$(PYTHON) -m ruff check apps/api apps/worker scripts/prepare-integration-database.py scripts/generate-openapi.py
	$(PYTHON) -m ruff format --check apps/api apps/worker scripts/prepare-integration-database.py scripts/generate-openapi.py
	npm run lint
	npm run format:check

typecheck:
	$(PYTHON) -m mypy apps/api/src apps/worker/src
	npm run typecheck

test:
	$(PYTHON) -m pytest apps/api/tests apps/worker/tests
	npm run test

build:
	npm run build

e2e:
	npm run test:e2e

e2e-list:
	npm run test:e2e:list

openapi:
	$(PYTHON) scripts/generate-openapi.py

smoke:
	./scripts/smoke-test-compose.sh

up:
	docker compose up --build -d

down:
	docker compose down --remove-orphans

logs:
	docker compose logs -f --tail=200

migrate:
	cd apps/api && ../../.venv/bin/alembic upgrade head

clean:
	rm -rf .venv node_modules apps/web/.next apps/web/node_modules packages/*/node_modules
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
