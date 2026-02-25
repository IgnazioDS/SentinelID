#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIGS = [
    ROOT / "apps" / "desktop" / "tauri.conf.json",
    ROOT / "apps" / "desktop" / "src-tauri" / "tauri.conf.json",
]

SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def validate(config_path: Path) -> None:
    require(config_path.exists(), f"missing config: {config_path}")

    payload = json.loads(config_path.read_text(encoding="utf-8"))
    package = payload.get("package")

    require(isinstance(package, dict), f"{config_path}: missing 'package' object")

    product_name = package.get("productName")
    version = package.get("version")

    require(isinstance(product_name, str) and product_name.strip(), f"{config_path}: package.productName is required")
    require(isinstance(version, str) and SEMVER.match(version), f"{config_path}: package.version must be semver (found: {version!r})")

    tauri = payload.get("tauri")
    require(isinstance(tauri, dict), f"{config_path}: missing 'tauri' object")

    bundle = tauri.get("bundle")
    require(isinstance(bundle, dict), f"{config_path}: tauri.bundle is required")
    identifier = bundle.get("identifier")
    require(isinstance(identifier, str) and identifier.strip(), f"{config_path}: tauri.bundle.identifier is required")


if __name__ == "__main__":
    try:
        for cfg in CONFIGS:
            validate(cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"tauri config validation failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print("tauri config validation passed")
