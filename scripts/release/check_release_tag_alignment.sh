#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${ROOT_DIR}"

EXPECTED_TAG="${RELEASE_EXPECT_TAG:-}"
if [[ -z "${EXPECTED_TAG}" ]]; then
  echo "Release tag alignment check skipped (set RELEASE_EXPECT_TAG=vX.Y.Z to enforce)"
  exit 0
fi

if ! git rev-parse --verify --quiet "${EXPECTED_TAG}^{tag}" >/dev/null 2>&1 \
  && ! git rev-parse --verify --quiet "${EXPECTED_TAG}^{commit}" >/dev/null 2>&1; then
  echo "Expected release tag not found: ${EXPECTED_TAG}"
  exit 1
fi

TAG_COMMIT="$(git rev-parse "${EXPECTED_TAG}^{}")"
HEAD_COMMIT="$(git rev-parse HEAD)"

echo "release_tag=${EXPECTED_TAG}"
echo "tag_commit=${TAG_COMMIT}"
echo "head_commit=${HEAD_COMMIT}"

if [[ "${TAG_COMMIT}" != "${HEAD_COMMIT}" ]]; then
  echo "Release tag alignment failed: ${EXPECTED_TAG} does not point to HEAD"
  exit 1
fi

echo "Release tag alignment check passed (${EXPECTED_TAG} -> HEAD)"
