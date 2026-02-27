# Release Guide (v2.1.1)

## Scope

This guide defines the reproducible release process for SentinelID, including security, reliability, and evidence generation gates.

## Canonical Preflight

Run from repository root:

```bash
make release-check
```

`make release-check` is the source-of-truth gate and includes:

- version consistency checks (`CHANGELOG.md`, `RUNBOOK.md`, `docs/RELEASE.md`, `docs/DEMO_CHECKLIST.md`, Makefile help banner)
- edge/cloud test suites
- desktop build checks
- docker build checks
- outage recovery smoke
- support bundle sanitization validation
- admin session-auth smoke
- orphan-edge process checks
- reliability SLO report export (`output/ci/reliability_slo.json`)
- release evidence pack generation (`output/release/evidence_pack_<timestamp>.tar.gz`)

## CI Parity

The repository includes a parity workflow:

- `.github/workflows/release-parity.yml`

It runs on PRs and `main` pushes and executes the full release checklist.

Repository maintainers must set **`release-parity` as a required branch protection check**.

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
- `docs/DEMO_CHECKLIST.md` header version
- `Makefile` help banner version
- `apps/desktop/src-tauri/tauri.conf.json` (`package.version`)

Use `./scripts/release/check_version_consistency.sh` before tagging to enforce alignment.

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
git switch -c branch/feat/release-vX.Y.Z
```

### 2) Run preflight and push branch

```bash
make release-check
git push -u origin branch/feat/release-vX.Y.Z
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
git merge --no-ff branch/feat/release-vX.Y.Z
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
- `scripts/perf/out/*.json` (edge perf evidence)
- `scripts/support/out/support_bundle_*.tar.gz`
- `output/release/evidence_pack_<timestamp>.tar.gz`
- support bundle sanitization pass logs
- cloud recovery smoke pass logs
- admin smoke pass logs

Build evidence pack manually (optional, outside full release-check):

```bash
make release-evidence
```

## Pilot Readiness Evidence (v2.3.1 target)

Build pilot evidence index (aggregates latest release evidence, docs snapshot, and checklist):

```bash
make pilot-evidence
```

Optional CI URL capture:

```bash
CI_PARITY_PR_URL="https://github.com/<org>/<repo>/actions/runs/<id>" \
CI_PARITY_MAIN_URL="https://github.com/<org>/<repo>/actions/runs/<id>" \
make pilot-evidence
```

Artifacts are written under `output/release/pilot_evidence_<timestamp>.tar.gz`.

## Post-Release

- Record final notes in `CHANGELOG.md`
- Ensure runbook/version headers stay aligned
- Keep release evidence linked from release notes
