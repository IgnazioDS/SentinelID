.PHONY: help \
	demo-up \
	demo-desktop \
	demo-desktop-verify \
	demo \
	demo-verify \
	demo-down \
	demo-checklist \
	check-no-orphans \
	check-no-duplicates \
	bundle-edge \
	check-edge-preflight \
	edge-shell \
	dev-edge \
	check-tauri-config \
	dev-desktop \
	check-desktop-ts \
	build-desktop-web \
	check-desktop-rust \
	build-desktop \
	test-edge \
	test-cloud \
	test \
	docker-build \
	smoke-edge \
	smoke-cloud \
	smoke-cloud-recovery \
	smoke-admin \
	smoke-desktop \
	smoke-bundling \
	perf-edge \
	support-bundle \
	runbook-lock \
	release-evidence \
	pilot-evidence \
	release-check \
	clean

help:
	@echo "SentinelID v2.3.5 Commands"
	@echo ""
	@echo "Demo"
	@echo "  make demo-up             Start cloud/admin/postgres and wait for health"
	@echo "  make demo-desktop        Launch desktop in demo mode (set DEMO_AUTO_CLOSE_SECONDS for scripted close)"
	@echo "  make demo                Run demo-up then demo-desktop"
	@echo "  make demo-verify         Run non-interactive demo verification suite"
	@echo "  make demo-desktop-verify Launch desktop and auto-close (CI-friendly, no Docker)"
	@echo "  make demo-down           Stop demo stack (use V=1 to remove volumes)"
	@echo "  make demo-checklist      Print demo checklist path (OPEN=1 to open locally)"
	@echo "  make check-no-orphans    Verify no orphan edge process is running"
	@echo "  make check-no-duplicates Verify duplicate source artifact pairs are absent"
	@echo ""
	@echo "Build"
	@echo "  make bundle-edge         Bundle edge runtime for desktop packaging"
	@echo "  make check-edge-preflight Validate edge Poetry env imports (pydantic_settings/uvicorn)"
	@echo "  make edge-shell          Open a shell inside edge Poetry environment"
	@echo "  make dev-edge            Run edge API locally (foreground)"
	@echo "  make check-tauri-config  Validate required Tauri config keys"
	@echo "  make check-desktop-ts    Run desktop TypeScript checks"
	@echo "  make build-desktop-web   Build desktop frontend"
	@echo "  make check-desktop-rust  Cargo check for Tauri runtime"
	@echo "  make build-desktop       Produce desktop distribution bundle (bundled edge runner)"
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
	@echo "  make smoke-cloud-recovery Validate edge outbox recovery through cloud outage"
	@echo "  make smoke-admin         Run admin smoke script"
	@echo "  make smoke-desktop       Run desktop launcher smoke script"
	@echo "  make smoke-bundling      Validate bundled desktop runtime (no Poetry at runtime)"
	@echo "  make perf-edge           Run edge benchmark (writes scripts/perf/out/*.json)"
	@echo "  make support-bundle      Generate sanitized support bundle artifact"
	@echo "  make runbook-lock        Build known-good runbook lock artifact under output/release/"
	@echo "  make release-evidence    Build release evidence pack under output/release/"
	@echo "  make pilot-evidence      Build pilot evidence index under output/release/"
	@echo "  make release-check       Run full release checklist"
	@echo ""
	@echo "Docs"
	@echo "  RUNBOOK.md is the authoritative run/test path"

bundle-edge:
	@./scripts/bundle_edge_venv.sh

demo-up:
	@./scripts/demo_up.sh

demo-desktop:
	@./scripts/demo_desktop.sh

demo-desktop-verify:
	@DEMO_AUTO_CLOSE_SECONDS="$${DEMO_AUTO_CLOSE_SECONDS:-20}" TELEMETRY_ENABLED=0 ALLOW_FALLBACK_EMBEDDINGS=1 ./scripts/demo_desktop.sh

demo: demo-up demo-desktop

demo-verify:
	@./scripts/demo_verify.sh

demo-down:
	@./scripts/demo_down.sh $(if $(V),--volumes,)

demo-checklist:
	@echo "$(PWD)/docs/DEMO_CHECKLIST.md"
	@if [ "$(OPEN)" = "1" ]; then \
		if command -v open >/dev/null 2>&1; then open "$(PWD)/docs/DEMO_CHECKLIST.md"; \
		elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$(PWD)/docs/DEMO_CHECKLIST.md"; \
		else echo "No opener found. Open docs/DEMO_CHECKLIST.md manually."; \
		fi; \
	fi

check-no-orphans:
	@./scripts/check_no_orphan_edge.sh

check-no-duplicates:
	@./scripts/release/check_no_duplicate_pairs.sh

check-edge-preflight:
	@./scripts/dev/edge_env.sh preflight

edge-shell:
	@./scripts/dev/edge_env.sh shell

dev-edge:
	@EDGE_ENV=dev EDGE_HOST=127.0.0.1 EDGE_PORT=8787 EDGE_AUTH_TOKEN=devtoken ALLOW_FALLBACK_EMBEDDINGS=$${ALLOW_FALLBACK_EMBEDDINGS:-1} ./scripts/dev/edge_env.sh run

check-tauri-config:
	@./scripts/dev/check_tauri_config.py

dev-desktop:
	@make check-tauri-config
	@cd apps/desktop && npm run tauri:dev

check-desktop-ts:
	@cd apps/desktop && npm run typecheck

build-desktop-web:
	@cd apps/desktop && npm run build

check-desktop-rust:
	@cd apps/desktop/src-tauri && cargo check

build-desktop: build-desktop-web check-desktop-rust
	@make check-tauri-config
	@[ -x apps/desktop/resources/edge/pyvenv/bin/python ] || (echo "Bundled edge runtime missing. Run 'make bundle-edge' first."; exit 1)
	@cd apps/desktop && npm run tauri:build

test-edge:
	@cd apps/edge && if command -v poetry >/dev/null 2>&1; then poetry run pytest -q; elif [ -x .venv/bin/poetry ]; then .venv/bin/poetry run pytest -q; else echo "Poetry not found. Install Poetry or create apps/edge/.venv with Poetry."; exit 1; fi

test-cloud:
	@cd apps/cloud && if [ -x .venv/bin/python ]; then .venv/bin/python -m pytest -q; else python3 -m pip install -r requirements-dev.txt >/dev/null && python3 -m pytest -q; fi

test: test-edge test-cloud

docker-build:
	@./scripts/docker_build.sh

smoke-edge:
	@./scripts/smoke_test_edge.sh

smoke-cloud:
	@./scripts/smoke_test_cloud.sh

smoke-cloud-recovery:
	@./scripts/smoke_test_cloud_recovery.sh

smoke-admin:
	@./scripts/smoke_test_admin.sh

smoke-desktop:
	@./scripts/smoke_test_desktop.sh

smoke-bundling:
	@./scripts/smoke_test_bundling.sh

perf-edge:
	@python3 scripts/perf/bench_edge.py --base-url http://127.0.0.1:8787 --token devtoken --attempts 8 --frames 12

support-bundle:
	@./scripts/support_bundle.sh

runbook-lock:
	@./scripts/release/build_runbook_lock.sh

release-evidence:
	@./scripts/release/build_evidence_pack.sh

pilot-evidence:
	@./scripts/release/build_pilot_evidence_index.sh

release-check:
	@./scripts/release/checklist.sh

clean:
	@rm -rf apps/desktop/resources/edge/pyvenv
	@rm -rf apps/desktop/src-tauri/target
	@rm -rf apps/desktop/dist
	@cd apps/edge && find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@cd apps/cloud && find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

.DEFAULT_GOAL := help
