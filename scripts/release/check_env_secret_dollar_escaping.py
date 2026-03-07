#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

SECRET_KEY_PATTERN = re.compile(r"(TOKEN|SECRET|PASSWORD|KEY|HASH)", re.IGNORECASE)


def is_literal_safe(value: str) -> bool:
    if not value:
        return True
    trimmed = value.strip()
    if trimmed.startswith("'") and trimmed.endswith("'"):
        return True
    sanitized = re.sub(r"\$\$", "", trimmed)
    return "$" not in sanitized


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    env_path = repo_root / ".env"
    if not env_path.exists():
        print("[skip] env secret dollar escaping (.env not present)")
        return 0

    failures: list[str] = []
    for lineno, raw_line in enumerate(env_path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            continue
        key, value = raw_line.split("=", 1)
        key = key.strip()
        if not SECRET_KEY_PATTERN.search(key):
            continue
        if "$" not in value or is_literal_safe(value):
            continue
        failures.append(
            f"{env_path}:{lineno}: {key} contains unescaped '$'. "
            "Use single quotes around the full value, escape as '$$', or prefer the *_B64 variant for Docker Compose."
        )

    if failures:
        print("Unsafe secret interpolation detected in .env:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("Env secret dollar escaping check passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
