#!/usr/bin/env bash

# Compose reads .env by default and interprets "$" patterns, which breaks
# legacy bcrypt hash values in ADMIN_UI_PASSWORD_HASH. This helper prepares a
# sanitized env file for docker compose commands when .env is present.

strip_wrapping_quotes() {
  local value="$1"
  if [[ "${value}" == \"*\" && "${value}" == *\" ]]; then
    value="${value#\"}"
    value="${value%\"}"
  elif [[ "${value}" == \'*\' && "${value}" == *\' ]]; then
    value="${value#\'}"
    value="${value%\'}"
  fi
  printf '%s' "${value}"
}

prepare_compose_env_file() {
  local repo_root="$1"
  local source_env="${repo_root}/.env"
  local tmp_env=""
  local hash_raw=""
  local has_hash_b64=0

  unset SENTINELID_COMPOSE_ENV_FILE
  if [[ ! -f "${source_env}" ]]; then
    return 0
  fi

  tmp_env="$(mktemp -t sentinelid_compose_env.XXXXXX)"
  while IFS= read -r line || [[ -n "${line}" ]]; do
    case "${line}" in
      ADMIN_UI_PASSWORD_HASH_B64=*)
        has_hash_b64=1
        printf '%s\n' "${line}" >> "${tmp_env}"
        ;;
      ADMIN_UI_PASSWORD_HASH=*)
        hash_raw="${line#ADMIN_UI_PASSWORD_HASH=}"
        ;;
      *)
        printf '%s\n' "${line}" >> "${tmp_env}"
        ;;
    esac
  done < "${source_env}"

  hash_raw="$(strip_wrapping_quotes "${hash_raw}")"
  if [[ "${has_hash_b64}" -eq 0 && -n "${hash_raw}" && "${hash_raw}" != "REPLACE_WITH_BCRYPT_HASH" ]]; then
    printf 'ADMIN_UI_PASSWORD_HASH_B64=%s\n' "$(printf '%s' "${hash_raw}" | base64 | tr -d '\n')" >> "${tmp_env}"
    echo "[compose-env] derived ADMIN_UI_PASSWORD_HASH_B64 from ADMIN_UI_PASSWORD_HASH"
  fi

  export SENTINELID_COMPOSE_ENV_FILE="${tmp_env}"
}

compose_cmd() {
  if [[ -n "${SENTINELID_COMPOSE_ENV_FILE:-}" ]]; then
    docker compose --env-file "${SENTINELID_COMPOSE_ENV_FILE}" "$@"
  else
    docker compose "$@"
  fi
}
