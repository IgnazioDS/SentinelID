from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DOCS_CONSISTENCY_SCRIPT = REPO_ROOT / "scripts" / "release" / "check_docs_consistency.sh"
FRESH_CLONE_SCRIPT = REPO_ROOT / "scripts" / "check_fresh_clone_bootstrap.sh"


def test_docs_root_has_no_phase_markdown_files() -> None:
    docs_root = REPO_ROOT / "docs"
    phase_files = sorted(path.name for path in docs_root.glob("phase*.md"))
    assert phase_files == []


def test_docs_consistency_script_passes() -> None:
    result = subprocess.run(
        [str(DOCS_CONSISTENCY_SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "Docs consistency check passed" in result.stdout


def test_fresh_clone_bootstrap_dry_run_uses_canonical_make_targets() -> None:
    result = subprocess.run(
        [str(FRESH_CLONE_SCRIPT), "--dry-run"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "install lockfile-managed dev dependencies" in result.stdout
    assert "install-dev" in result.stdout
    assert "demo-up" in result.stdout
    assert "demo-verify" in result.stdout
    assert "demo-down" in result.stdout
