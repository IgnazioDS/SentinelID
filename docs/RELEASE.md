# Release Guide (v1.0.0)

## Scope

This guide defines the reproducible release process for SentinelID.

## Pre-Tag Checklist

Run from repository root:

```bash
make test
make build-desktop-web
make check-desktop-rust
make docker-build
make smoke-edge
make smoke-cloud
make smoke-admin
make smoke-desktop
make smoke-bundling
make perf-edge
```

One-command equivalent:

```bash
make release-check
```

## Packaging Validation

```bash
make bundle-edge
make build-desktop
```

## Version Bump Locations

When cutting a new release, review/update:

- `CHANGELOG.md` (new version section)
- `apps/desktop/src-tauri/tauri.conf.json` (`package.version`)
- Any release references in docs (for example `RUNBOOK.md`, `README.md`)

## Tagging Rules

- Pre-release tag format: `vX.Y.Z-rc.N`
- Stable tag format: `vX.Y.Z`
- Tag on the merge commit in `main` for stable releases.

## Release Cut Commands

### 1) Prepare release branch

```bash
git switch main
git pull
git switch -c branch/feat/release-v1.0.0
```

### 2) Push branch and pre-release tag

```bash
git push -u origin branch/feat/release-v1.0.0
git tag -a v1.0.0-rc.1 -m "SentinelID v1.0.0 release candidate 1"
git push origin v1.0.0-rc.1
```

### 3) Merge to main (no squash)

```bash
git switch main
git pull
git merge --no-ff branch/feat/release-v1.0.0
git push origin main
```

### 4) Create stable release tag

```bash
git tag -a v1.0.0 -m "SentinelID v1.0.0"
git push origin v1.0.0
git show --no-patch --decorate v1.0.0
```

## Artifacts

Expected release artifacts:

- Desktop bundle from `make build-desktop`
- Cloud and admin images from `make docker-build`
- Smoke and benchmark outputs from `scripts/eval/out/`
