.PHONY: help dev-desktop dev-edge dev-cloud dev-admin gen-types lint test

help:
	@echo "Makefile for SentinelID Development"
	@echo ""
	@echo "Usage:"
	@echo "    make dev-desktop         - Run the desktop app in development mode"
	@echo "    make dev-edge            - Run the local edge service in development mode"
	@echo "    make dev-cloud           - Run the remote cloud stack (cloud API + admin UI) via Docker Compose"
	@echo "    make dev-admin           - (If running standalone) Run the admin UI in development mode"
	@echo "    make gen-types           - Generate TypeScript types from OpenAPI schemas"
	@echo "    make lint                - Lint all applications"
	@echo "    make test                - Run tests for all applications"
	@echo ""

# Development commands
dev-desktop:
	@echo "Starting desktop app development server..."
	cd apps/desktop && npm run tauri dev

dev-edge:
	@echo "Starting edge service development server..."
	cd apps/edge && poetry run uvicorn sentinelid_edge.main:app --reload

dev-cloud:
	@echo "Starting remote cloud stack (API + Admin Dashboard)..."
	docker-compose up --build

dev-admin:
	@echo "Starting admin dashboard development server..."
	cd apps/admin && npm run dev

# Tooling
gen-types:
	@echo "Generating types from schemas..."
	./scripts/gen_types.sh

lint:
	@echo "Linting not yet configured."

test:
	@echo "Testing not yet configured."

