#!/usr/bin/env bash
set -euo pipefail

PORT="${PORT:-3000}"
# Best-effort OCR login is OFF by default (VTOP's CAPTCHA defeats OCR).
# Set VTOP_OCR_AUTOLOGIN=true to attempt it anyway at startup.
OCR_AUTOLOGIN="${VTOP_OCR_AUTOLOGIN:-false}"

echo "=================================================================="
echo " vtop-mcp container starting"

# CAPTCHA helper dir: make it exist so TMPDIR-based captcha capture works
# even before the host-side volume is populated.
mkdir -p /app/.vtop-session/captcha 2>/dev/null || true

has_valid_session() {
  local out
  out="$(vtop-mcp status 2>&1 || true)"
  [[ "$out" == *"session_valid=true"* ]]
}

if has_valid_session; then
  echo " existing VTOP session is valid - skipping login."
elif [[ "$OCR_AUTOLOGIN" == "true" ]]; then
  echo " no valid session - attempting best-effort automated login (OCR)."
  if python -m vtop_mcp.auto_login; then
    echo " automated login succeeded."
  else
    echo "!! automated login failed." >&2
  fi
else
  echo " no valid session - start the server now; log in interactively when ready."
  echo "   Manual login:  docker exec -it vtop-mcp vtop-mcp login"
  echo "   Need to re-login after the ~6h session age or when VTOP expires it."
fi

echo "------------------------------------------------------------------"
exec supergateway --stdio "python -m mcp_server" --port "$PORT" \
  --outputTransport streamableHttp --streamableHttpPath /mcp