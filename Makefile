.PHONY: help \
	bundle-edge \
	dev-edge \
	dev-desktop \
	build-desktop-web \
	check-desktop-rust \
	build-desktop \
	test-edge \
	test-cloud \
	test \
	docker-build \
	smoke-edge \
	smoke-cloud \
	smoke-admin \
	smoke-desktop \
	smoke-bundling \
	perf-edge \
	release-check \
	clean

help:
	@echo "SentinelID v1.0.2 Commands"
	@echo ""
	@echo "Build"
	@echo "  make bundle-edge         Bundle edge runtime for desktop packaging"
	@echo "  make dev-edge            Run edge API locally (foreground)"
	@echo "  make build-desktop-web   Build desktop frontend"
	@echo "  make check-desktop-rust  Cargo check for Tauri runtime"
	@echo "  make build-desktop       Produce desktop bundle (requires Tauri deps)"
	@echo ""
	@echo "Test"
	@echo "  make test-edge           Run edge pytest suite"
	@echo "  make test-cloud          Run cloud pytest suite"
	@echo "  make test                Run edge + cloud tests"
	@echo ""
	@echo "Validation"
	@echo "  make docker-build        Build cloud/admin Docker images"
	@echo "  make smoke-edge          Run edge smoke script"
	@echo "  make smoke-cloud         Run cloud smoke script"
	@echo "  make smoke-admin         Run admin smoke script"
	@echo "  make smoke-desktop       Run desktop launcher smoke script"
	@echo "  make smoke-bundling      Run desktop bundling smoke script"
	@echo "  make perf-edge           Run edge benchmark"
	@echo "  make release-check       Run full release checklist"
	@echo ""
	@echo "Docs"
	@echo "  RUNBOOK.md is the authoritative run/test path"

bundle-edge:
	@./scripts/bundle_edge_venv.sh

dev-edge:
	@cd apps/edge && if command -v poetry >/dev/null 2>&1; then EDGE_ENV=dev EDGE_HOST=127.0.0.1 EDGE_PORT=8787 EDGE_AUTH_TOKEN=devtoken poetry run uvicorn sentinelid_edge.main:app --host 127.0.0.1 --port 8787; elif [ -x .venv/bin/poetry ]; then EDGE_ENV=dev EDGE_HOST=127.0.0.1 EDGE_PORT=8787 EDGE_AUTH_TOKEN=devtoken .venv/bin/poetry run uvicorn sentinelid_edge.main:app --host 127.0.0.1 --port 8787; else echo "Poetry not found. Install Poetry or create apps/edge/.venv with Poetry."; exit 1; fi

dev-desktop: bundle-edge
	@cd apps/desktop && npm run tauri dev

build-desktop-web:
	@cd apps/desktop && npm run build

check-desktop-rust:
	@cd apps/desktop/src-tauri && cargo check

build-desktop: bundle-edge build-desktop-web check-desktop-rust
	@cd apps/desktop && npm run tauri build

test-edge:
	@cd apps/edge && if command -v poetry >/dev/null 2>&1; then poetry run pytest -q; elif [ -x .venv/bin/poetry ]; then .venv/bin/poetry run pytest -q; else echo "Poetry not found. Install Poetry or create apps/edge/.venv with Poetry."; exit 1; fi

test-cloud:
	@cd apps/cloud && if [ -x .venv/bin/python ]; then .venv/bin/python -m pytest -q; else python3 -m pip install -r requirements-dev.txt >/dev/null && python3 -m pytest -q; fi

test: test-edge test-cloud

docker-build:
	@docker compose build cloud admin

smoke-edge:
	@./scripts/smoke_test_edge.sh

smoke-cloud:
	@./scripts/smoke_test_cloud.sh

smoke-admin:
	@./scripts/smoke_test_admin.sh

smoke-desktop:
	@./scripts/smoke_test_desktop.sh

smoke-bundling:
	@./scripts/smoke_test_bundling.sh

perf-edge:
	@python3 scripts/perf/bench_edge.py --base-url http://127.0.0.1:8787 --token devtoken --attempts 8 --frames 12

release-check:
	@./scripts/release/checklist.sh

clean:
	@rm -rf apps/desktop/resources/edge/pyvenv
	@rm -rf apps/desktop/src-tauri/target
	@rm -rf apps/desktop/dist
	@cd apps/edge && find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@cd apps/cloud && find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

.DEFAULT_GOAL := help
