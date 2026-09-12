#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-3000}"

echo "=================================================================="
echo " vtop-mcp container starting"

has_valid_session() {
  local out
  out="$(vtop-mcp status 2>&1 || true)"
  [[ "$out" == *"session_valid=true"* ]]
}

if has_valid_session; then
  echo " existing VTOP session is valid - skipping login."
else
  echo " no valid session - running automated login (Tesseract OCR)."
  if python -m vtop_mcp.auto_login; then
    echo " automated login succeeded."
  else
    echo "!! automated login failed - it will retry automatically on next start." >&2
  fi
fi

echo "------------------------------------------------------------------"
exec supergateway --stdio "vtop-mcp serve" --port "$PORT" \
  --outputTransport streamableHttp --streamableHttpPath /mcp