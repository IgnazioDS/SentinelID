.PHONY: help bundle-edge dev-desktop build-desktop clean test

help:
	@echo "SentinelID Build Commands"
	@echo ""
	@echo "Desktop/Tauri:"
	@echo "  make bundle-edge       - Bundle edge runtime for Tauri packaging"
	@echo "  make dev-desktop       - Run Tauri desktop app in development mode"
	@echo "  make build-desktop     - Build production Tauri desktop app"
	@echo ""
	@echo "Development:"
	@echo "  make test              - Run all tests"
	@echo "  make clean             - Clean build artifacts"
	@echo ""
	@echo "Documentation:"
	@echo "  see docs/PACKAGING.md   - Desktop packaging guide"
	@echo "  see docs/RECOVERY.md    - Telemetry recovery guide"

## Desktop Packaging

bundle-edge:
	@echo "Bundling edge runtime for Tauri..."
	@./scripts/bundle_edge_venv.sh
	@echo ""
	@echo "Next steps:"
	@echo "  - Verify resources: ls -la apps/desktop/resources/edge/"
	@echo "  - Build app: make build-desktop"

dev-desktop: bundle-edge
	@echo "Starting Tauri desktop in dev mode..."
	@cd apps/desktop && npm run tauri dev

build-desktop: bundle-edge
	@echo "Building production Tauri desktop app..."
	@cd apps/desktop && npm run tauri build
	@echo ""
	@echo "Build complete! Check ./apps/desktop/src-tauri/target/release/"

## Utilities

test:
	@echo "Running tests..."
	@cd apps/edge && pytest -v
	@cd apps/cloud && pytest -v

clean:
	@echo "Cleaning build artifacts..."
	@rm -rf apps/desktop/resources/edge/pyvenv
	@rm -rf apps/desktop/src-tauri/target
	@rm -rf apps/desktop/dist
	@cd apps/edge && find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@cd apps/cloud && find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean complete"

.DEFAULT_GOAL := help
