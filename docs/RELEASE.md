# Release Guide (v2.5.0)

## Scope

This guide defines the reproducible release process for SentinelID, including security, reliability, and evidence generation gates.

## Canonical Preflight

Run from repository root:

```bash
make release-check
```

`make release-check` is the source-of-truth gate and includes:

- version consistency checks (`CHANGELOG.md`, `RUNBOOK.md`, `docs/RELEASE.md`, `docs/PACKAGING.md`, `docs/RECOVERY.md`, `docs/DEMO_CHECKLIST.md`, `docs/PILOT_FREEZE.md`, Makefile help banner, cloud API metadata)
- `.env` secret interpolation guard for unescaped `$` in secret values
- desktop package/config version consistency checks (`apps/desktop/package.json`, `apps/desktop/package-lock.json`, `apps/desktop/tauri.conf.json`, `apps/desktop/src-tauri/tauri.conf.json`, `apps/desktop/src-tauri/tauri.dev.conf.json`)
- optional strict tag-to-HEAD alignment (`RELEASE_EXPECT_TAG=vX.Y.Z`)
- preflight quarantine for untracked duplicate desktop-edge artifacts
- duplicate artifact pair guard (`scripts/release/check_no_duplicate_pairs.sh`)
- edge/cloud test suites
- desktop build checks
- runtime invariant smoke report (`output/ci/invariant_report.json`)
- desktop warning-noise budget summary (`output/ci/desktop_warning_budget.json`)
- desktop/admin token exposure checks for built client bundles
- docker build checks
- outage recovery smoke
- support bundle sanitization validation
- local support bundle artifact sanitization validation
- admin session-auth smoke
- orphan-edge process checks
- tracked git status unchanged guard (no tracked-file mutations during gate)
- reliability SLO report export (`output/ci/reliability_slo.json`)
- release evidence pack generation (`output/release/evidence_pack_<timestamp>.tar.gz`)

Interpret the new machine-readable artifacts as follows:

- `output/ci/invariant_report.json`: runtime contract probe for loopback binding, edge bearer enforcement, cloud admin token enforcement, and support-bundle endpoint behavior. Any failed check is a release blocker.
- `output/ci/desktop_warning_budget.json`: desktop Rust warning summary generated from the captured cargo log. It fails when `warning_count > DESKTOP_WARNING_BUDGET` and lists the highest-noise sources first.

## CI Parity

The repository includes a parity workflow:

- `.github/workflows/release-parity.yml`

It runs on PRs and `main` pushes and executes the full release checklist.

Repository maintainers must set **`release-parity` as a required branch protection check**.
Fast workflows (`edge-tests`, `cloud-tests`, `desktop-build`, `docker-build`) remain enabled for quick feedback but do not replace parity gating.

Parity workflow controls:

- retried parity execution (`scripts/ci/run_release_parity.sh`, default 2 attempts)
- compose cleanup between retry attempts
- uploaded parity diagnostics (`output/ci/logs/release_check_attempt_*.log`, compose `ps`, compose logs)
- retained release parity artifacts for 14 days
- release and smoke failure diagnostics exported to `output/ci/logs/` (`release_check_failure_*`, `cloud_smoke_failure_*`, `cloud_recovery_failure_*`)

## Packaging Validation

```bash
make bundle-edge
make build-desktop
```

## Version Bump Locations

When cutting a new release, review/update:

- `CHANGELOG.md` (new version section)
- `RUNBOOK.md` header version
- `docs/RELEASE.md` header version
- `docs/PACKAGING.md` header version
- `docs/RECOVERY.md` header version
- `docs/DEMO_CHECKLIST.md` header version
- `docs/PILOT_FREEZE.md` target version
- `Makefile` help banner version
- `apps/cloud/main.py` (`FastAPI(..., version=...)`)
- `apps/desktop/package.json` (`version`)
- `apps/desktop/package-lock.json` (`version`)
- `apps/desktop/tauri.conf.json` (`package.version`)
- `apps/desktop/src-tauri/tauri.conf.json` (`package.version`)
- `apps/desktop/src-tauri/tauri.dev.conf.json` (`package.version`)

Use `./scripts/release/check_version_consistency.sh` before tagging to enforce alignment.

Use `./scripts/release/check_release_tag_alignment.sh` to enforce that a specific tag points to HEAD:

```bash
RELEASE_EXPECT_TAG=vX.Y.Z ./scripts/release/check_release_tag_alignment.sh
RELEASE_EXPECT_TAG=vX.Y.Z make check-release-tag
```

## Canonical Orphan-Check Command

- Canonical path: `scripts/check_no_orphan_edge.sh`
- `scripts/release/check_no_orphan_edge.sh` remains as a compatibility wrapper for legacy references.

## Tagging Rules

- Pre-release tag format: `vX.Y.Z-rc.N`
- Stable tag format: `vX.Y.Z`
- Stable tags are created from the merge commit in `main`.

## Release Cut Commands

### 1) Prepare release branch

```bash
git switch main
git pull
git switch -c branch/release-vX.Y.Z
```

### 2) Run preflight and push branch

```bash
make release-check
RELEASE_EXPECT_TAG=vX.Y.Z make release-check
git push -u origin branch/release-vX.Y.Z
```

### 3) Optional release-candidate tag

```bash
git tag -a vX.Y.Z-rc.1 -m "SentinelID vX.Y.Z release candidate 1"
git push origin vX.Y.Z-rc.1
```

### 4) Merge to main (no squash)

```bash
git switch main
git pull
git merge --no-ff branch/release-vX.Y.Z
git push origin main
```

### 5) Create stable release tag

```bash
git tag -a vX.Y.Z -m "SentinelID vX.Y.Z"
git push origin vX.Y.Z
git show --no-patch --decorate vX.Y.Z
```

## Required Evidence Artifacts

Before publishing a stable release, confirm these artifacts exist and are attached/stored:

- `output/ci/reliability_slo.json`
- `output/ci/invariant_report.json`
- `output/ci/desktop_warning_budget.json`
- `scripts/perf/out/*.json` (edge perf evidence)
- `scripts/support/out/support_bundle_*.tar.gz`
- `output/release/evidence_pack_<timestamp>.tar.gz`
- support bundle sanitization pass logs
- cloud recovery smoke pass logs
- admin smoke pass logs
- successful `release-tag` `workflow_dispatch` run URL (post-release validation)
- known-good runbook lock artifact (`runbook_lock_<label>.tar.gz`)
- release assets on the tagged GitHub release:
  - `evidence_pack_<tag>.tar.gz`
  - `pilot_evidence_<tag>.tar.gz`
  - `runbook_lock_<tag>.tar.gz`

Build evidence pack manually (optional, outside full release-check):

```bash
make release-evidence
```

Build known-good runbook lock artifact manually:

```bash
make runbook-lock
```

## Pilot Readiness Evidence (v2.5.0 target)

Build pilot evidence index (aggregates latest release evidence, docs snapshot, and checklist):

```bash
make pilot-evidence
```

Optional CI URL capture:

```bash
CI_PARITY_PR_URL="https://github.com/<org>/<repo>/actions/runs/<id>" \
CI_PARITY_MAIN_URL="https://github.com/<org>/<repo>/actions/runs/<id>" \
RELEASE_TAG_DISPATCH_URL="https://github.com/<org>/<repo>/actions/runs/<id>" \
RUNBOOK_LOCK_LABEL="vX.Y.Z" \
make pilot-evidence
```

Artifacts are written under `output/release/pilot_evidence_<timestamp>.tar.gz`.

## Post-Release

- Record final notes in `CHANGELOG.md`
- Ensure runbook/version headers stay aligned
- Keep release evidence linked from release notes
- For stable tags (`vX.Y.Z`), `.github/workflows/release-tag.yml` now builds and uploads:
  - `evidence_pack_<tag>.tar.gz`
  - `pilot_evidence_<tag>.tar.gz`
  - `runbook_lock_<tag>.tar.gz`
- Optional manual release-pipeline validation without creating a new tag:

```bash
gh workflow run release-tag.yml --ref main
```

- Capture the successful run URL in pilot evidence (optional; auto-detected when possible):

```bash
RELEASE_TAG_DISPATCH_URL="https://github.com/<org>/<repo>/actions/runs/<id>" make pilot-evidence
```
