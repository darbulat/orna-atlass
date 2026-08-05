#!/usr/bin/env bash
set -euo pipefail

TIMEOUT="${ADMIN_SMOKE_TIMEOUT:-8}"
LOCAL_URL="${ADMIN_SMOKE_LOCAL_URL:-http://127.0.0.1:3000/admin}"
GATEWAY_HTTP="${ADMIN_SMOKE_GATEWAY_HTTP_URL:-http://127.0.0.1/admin}"
GATEWAY_HOST="${ADMIN_SMOKE_GATEWAY_HOST:-orna.land}"
GATEWAY_HTTPS="${ADMIN_SMOKE_GATEWAY_HTTPS_URL:-https://${GATEWAY_HOST}/admin}"
API_BASE_URL="${ADMIN_SMOKE_API_BASE_URL:-https://${GATEWAY_HOST}/api/v1}"

pass=true

require_status_eq() {
  local code="$1"
  local expected="$2"
  local label="$3"

  if [[ "${code}" == "${expected}" ]]; then
    echo "[OK] ${label}"
  else
    echo "[FAIL] ${label}: got ${code} expected ${expected}"
    pass=false
  fi
}

require_redirect_like() {
  local code="$1"
  local label="$2"

  case "${code}" in
    301|302|307|308)
      echo "[OK] ${label}: ${code}"
      ;;
    "")
      echo "[FAIL] ${label}: unknown status"
      pass=false
      ;;
    *)
      echo "[FAIL] ${label}: status=${code}"
      pass=false
      ;;
  esac
}

require_contains() {
  local file="$1"
  local pattern="$2"
  local label="$3"

  if grep -Fq -- "$pattern" "$file"; then
    echo "[OK] ${label}: ${pattern}"
  else
    echo "[FAIL] ${label}: pattern not found -> ${pattern}"
    pass=false
  fi
}

status_from_headers() {
  awk 'NR==1{print $2}' "$1"
}

# 1) Local Next.js route should be reachable and render admin shell
temp_root="$(mktemp -d)"
trap 'rm -rf "${temp_root}"' EXIT

local_html="${temp_root}/admin_local.html"
local_headers="${temp_root}/admin_local_headers.txt"
curl -sS -m "${TIMEOUT}" -D "${local_headers}" -o "${local_html}" "${LOCAL_URL}"
local_code="$(status_from_headers "${local_headers}")"
require_status_eq "${local_code}" "200" "Локальный /admin отвечает 200"
if grep -Eiq '^Cache-Control:.*no-store' "${local_headers}"; then
  echo "[OK] Локальный /admin запрещает хранение ответа (Cache-Control: no-store)"
else
  echo "[FAIL] Локальный /admin не вернул Cache-Control: no-store"
  pass=false
fi

if [[ -f "${local_html}" ]]; then
  tr '<' '\n' <"${local_html}" >"${temp_root}/admin_local_split.txt"
  require_contains "${temp_root}/admin_local_split.txt" "admin-shell" "Локальный HTML содержит admin-shell"
  require_contains "${temp_root}/admin_local_split.txt" "Админ-панель" "Локальный HTML показывает auth-заглушку"
fi

# 2) Параметризованный запрос содержит только bounded non-sensitive state.
query_encoded="$(python3 - <<'PY'
import urllib.parse
params = {
    "notice": "Операция выполнена.",
    "notice_kind": "success",
    "notice_section": "Smoke",
    "locations_limit": "50",
    "sessions_limit": "50",
}
print(urllib.parse.urlencode(params, safe=""))
PY
)"
query_html="${temp_root}/admin_query.html"
query_headers="${temp_root}/admin_query_headers.txt"
query_url="${LOCAL_URL}?${query_encoded}"

curl -sS -m "${TIMEOUT}" -D "${query_headers}" -o "${query_html}" "$query_url"
query_code="$(status_from_headers "${query_headers}")"
require_status_eq "${query_code}" "200" "Параметризованный локальный /admin отвечает 200"

if [[ "${query_url}" == *"operation_log"* || "${query_url}" == *"user_email"* || "${query_url}" == *"audit_ip_address"* || "${query_url}" == *"audit_user_agent"* ]]; then
  echo "[FAIL] URL содержит запрещённое privacy-sensitive состояние"
  pass=false
else
  echo "[OK] URL не содержит operation log, email, IP или user-agent"
fi

if [[ -f "${query_html}" ]]; then
  tr '<' '\n' <"${query_html}" >"${temp_root}/admin_query_split.txt"
  require_contains "${temp_root}/admin_query_split.txt" "admin-shell" "Параметризированный запрос сохранил базовый shell"
fi

# 3) Gateway redirect check
curl -sS -I -m "${TIMEOUT}" "${GATEWAY_HTTP}" -o "${temp_root}/gateway_headers.txt" >/dev/null
gateway_code="$(status_from_headers "${temp_root}/gateway_headers.txt")"
if [[ -n "${gateway_code}" ]]; then
  require_redirect_like "${gateway_code}" "HTTP /admin через gateway должен редиректить в HTTPS"
else
  echo "[FAIL] Не удалось прочитать status у HTTP gateway"
  pass=false
fi
location_value="$(grep -i '^Location:' "${temp_root}/gateway_headers.txt" | tail -n 1 | cut -d' ' -f2- | tr -d '\r')"
if [[ -n "${location_value}" ]]; then
  echo "[INFO] Location: ${location_value}"
fi

# 4) HTTPS gateway smoke. Resolve the public hostname locally so certificate verification stays enabled.
curl -sS -I -m "${TIMEOUT}" --resolve "${GATEWAY_HOST}:443:127.0.0.1" "${GATEWAY_HTTPS}" -o "${temp_root}/https_headers.txt" >/dev/null || true
https_code="$(status_from_headers "${temp_root}/https_headers.txt")"
if [[ -n "${https_code}" ]]; then
  if [[ "${https_code}" == "200" ]]; then
    echo "[OK] HTTPS /admin возвращает 200."
  elif [[ "${https_code}" == "404" ]]; then
    echo "[FAIL] HTTPS /admin возвращает 404: gateway не обслуживает admin route текущего кандидата." >&2
    exit 1
  else
    echo "[FAIL] HTTPS /admin возвращает неожиданный статус ${https_code}." >&2
    exit 1
  fi
else
  echo "[FAIL] Не удалось прочитать статус HTTPS /admin."
  pass=false
fi

# 5) Read-only API auth and shape probes. Credential values are read only from environment and
# written to mode-600 temporary curl config files, never command arguments, URLs, or output.
api_request() {
  local label="$1"
  local expected="$2"
  local path="$3"
  local credential_config="${4:-}"
  local prefix="$5"
  local headers_file="${temp_root}/${prefix}_headers.txt"
  local body_file="${temp_root}/${prefix}_body.json"
  local url="${API_BASE_URL}${path}"
  local code

  if [[ -n "${credential_config}" ]]; then
    if ! curl -sS -m "${TIMEOUT}" --resolve "${GATEWAY_HOST}:443:127.0.0.1" \
      --config "${credential_config}" -D "${headers_file}" -o "${body_file}" "${url}"; then
      echo "[FAIL] ${label}: API request failed"
      pass=false
      return
    fi
  else
    if ! curl -sS -m "${TIMEOUT}" --resolve "${GATEWAY_HOST}:443:127.0.0.1" \
      -D "${headers_file}" -o "${body_file}" "${url}"; then
      echo "[FAIL] ${label}: API request failed"
      pass=false
      return
    fi
  fi
  code="$(status_from_headers "${headers_file}")"
  require_status_eq "${code}" "${expected}" "${label}"
  if [[ "${expected}" == "200" ]] && ! grep -Eiq '^Cache-Control:.*no-store' "${headers_file}"; then
    echo "[FAIL] ${label}: отсутствует Cache-Control: no-store"
    pass=false
  fi
}

write_cookie_config() {
  local file="$1"
  local value="$2"
  umask 077
  printf 'cookie = "orna_access=%s"\n' "${value}" >"${file}"
}

api_request "Anonymous admin identity deny" "401" "/admin/me" "" "anonymous_me"

if [[ -n "${ADMIN_SMOKE_MEMBER_COOKIE:-}" ]]; then
  member_config="${temp_root}/member.curl.conf"
  write_cookie_config "${member_config}" "${ADMIN_SMOKE_MEMBER_COOKIE}"
  api_request "Member admin identity deny" "403" "/admin/me" "${member_config}" "member_me"
else
  echo "[SKIP] Member denial probe: ADMIN_SMOKE_MEMBER_COOKIE is not set"
fi

if [[ -n "${ADMIN_SMOKE_ADMIN_COOKIE:-}" ]]; then
  admin_config="${temp_root}/admin.curl.conf"
  write_cookie_config "${admin_config}" "${ADMIN_SMOKE_ADMIN_COOKIE}"
  api_request "Admin identity read" "200" "/admin/me" "${admin_config}" "admin_me"
  api_request "Admin location read" "200" "/admin/locations?limit=1&offset=0" "${admin_config}" "admin_locations"
  api_request "Admin audit read" "200" "/admin/audit-events?limit=1&offset=0" "${admin_config}" "admin_audit"
  python3 - "${temp_root}/admin_me_body.json" "${temp_root}/admin_locations_body.json" "${temp_root}/admin_audit_body.json" <<'PY'
import json
import sys

identity = json.load(open(sys.argv[1], encoding="utf-8"))
locations = json.load(open(sys.argv[2], encoding="utf-8"))
audits = json.load(open(sys.argv[3], encoding="utf-8"))
if not isinstance(identity, dict) or identity.get("role") != "admin":
    raise SystemExit("admin identity response shape is invalid")
if not isinstance(locations, list):
    raise SystemExit("admin locations response shape is invalid")
if not isinstance(audits, list):
    raise SystemExit("admin audit response shape is invalid")
PY
  echo "[OK] Authenticated admin response shapes are valid"
else
  echo "[SKIP] Authenticated admin probes: ADMIN_SMOKE_ADMIN_COOKIE is not set"
fi

if [[ "${pass}" == "true" ]]; then
  echo "[PASS] Смоук-чеки /admin пройдены."
  exit 0
fi

echo "[FAIL] Смоук-чеки /admin не пройдены."
exit 1
