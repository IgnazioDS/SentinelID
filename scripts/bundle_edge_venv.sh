#!/usr/bin/env bash
set -euo pipefail
export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_INPUT=1

# Bundle Edge runtime into desktop resources in a reproducible way.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
DESKTOP_APP="${PROJECT_ROOT}/apps/desktop"
EDGE_APP="${PROJECT_ROOT}/apps/edge"
RESOURCES_DIR="${DESKTOP_APP}/resources/edge"
VENV_DIR="${RESOURCES_DIR}/pyvenv_active"
APP_FALLBACK_DIR="${RESOURCES_DIR}/app"
RUNNER_PATH="${RESOURCES_DIR}/run_edge.sh"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if ! command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
  echo "Python interpreter not found: ${PYTHON_BIN}"
  exit 1
fi

POETRY_BIN=""
if command -v poetry >/dev/null 2>&1; then
  POETRY_BIN="$(command -v poetry)"
elif [[ -x "${EDGE_APP}/.venv/bin/poetry" ]]; then
  POETRY_BIN="${EDGE_APP}/.venv/bin/poetry"
fi

if [[ -z "${POETRY_BIN}" ]]; then
  echo "Poetry is required for deterministic edge bundling. Install Poetry or ensure ${EDGE_APP}/.venv/bin/poetry exists."
  exit 1
fi

echo "Bundling Edge runtime for desktop distribution"
echo "  edge app: ${EDGE_APP}"
echo "  resources: ${RESOURCES_DIR}"

mkdir -p "${RESOURCES_DIR}"
rm -rf "${APP_FALLBACK_DIR}"
if [[ -d "${VENV_DIR}" ]]; then
  "${PYTHON_BIN}" -m venv --clear "${VENV_DIR}"
else
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "${TMP_DIR}"
}
trap cleanup EXIT

WHEEL_DIR="${TMP_DIR}/wheelhouse"
mkdir -p "${WHEEL_DIR}"

echo "Installing edge runtime dependencies from poetry.lock"
echo "  using Poetry lock install into bundled venv (plugin-free)"
(
  cd "${EDGE_APP}"
  VIRTUAL_ENV="${VENV_DIR}" \
  PATH="${VENV_DIR}/bin:${PATH}" \
  POETRY_VIRTUALENVS_CREATE=false \
  "${POETRY_BIN}" install --only main --no-root --sync
)

echo "Installing dependencies into bundled venv"
"${VENV_DIR}/bin/python" -m pip install --upgrade pip setuptools wheel
# Desktop distribution is headless; remove GUI opencv wheels if both are present.
if "${VENV_DIR}/bin/pip" show opencv-python-headless >/dev/null 2>&1; then
  "${VENV_DIR}/bin/pip" uninstall -y opencv-python >/dev/null 2>&1 || true
  # Both OpenCV wheels share the cv2 package namespace. Reinstall headless after
  # removing GUI wheel so cv2 files are guaranteed present.
  OPENCV_HEADLESS_VER="$("${VENV_DIR}/bin/pip" show opencv-python-headless | awk '/^Version:/{print $2}')"
  if [[ -n "${OPENCV_HEADLESS_VER}" ]]; then
    "${VENV_DIR}/bin/pip" install --force-reinstall --no-deps "opencv-python-headless==${OPENCV_HEADLESS_VER}"
  fi
fi

# poetry.lock is currently out of sync with pyproject (keyring omitted) and
# cryptography is required by edge encryption code; install explicit runtime deps.
"${VENV_DIR}/bin/pip" install keyring==24.3.1 cryptography==46.0.3 httpx==0.25.2

echo "Building edge wheel and installing into bundled venv"
(
  cd "${EDGE_APP}"
  rm -f dist/*.whl
  "${POETRY_BIN}" build -f wheel
  EDGE_WHEEL="$(ls -1t dist/*.whl | head -n 1)"
  cp "${EDGE_WHEEL}" "${WHEEL_DIR}/"
)
"${VENV_DIR}/bin/pip" install --no-deps "${WHEEL_DIR}"/*.whl

if ! "${VENV_DIR}/bin/python" -m uvicorn --version >/dev/null 2>&1; then
  echo "uvicorn missing after bundle install"
  exit 1
fi

if ! "${VENV_DIR}/bin/python" -c "import sentinelid_edge.main" >/dev/null 2>&1; then
  echo "sentinelid_edge import check failed in bundled runtime"
  exit 1
fi

echo "Copying edge source fallback for PYTHONPATH runtime fallback"
mkdir -p "${APP_FALLBACK_DIR}"
cp -R "${EDGE_APP}/sentinelid_edge" "${APP_FALLBACK_DIR}/"

if [[ ! -f "${RUNNER_PATH}" ]]; then
  echo "Missing bundled runner at ${RUNNER_PATH}"
  exit 1
fi
chmod +x "${RUNNER_PATH}"

echo "Bundle complete"
echo "  bundled python: ${VENV_DIR}/bin/python"
echo "  runner: ${RUNNER_PATH}"
