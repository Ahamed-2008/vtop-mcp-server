#!/usr/bin/env bash
# Interactive VTOP login inside the vtop-mcp container that auto-opens the
# CAPTCHA image on the HOST (via xdg-open) as soon as it is written.
#
# Requires the container to be running with the project's .vtop-session volume
# mounted at /app/.vtop-session (see README / docker docs) and the container
# named "vtop-mcp" (override with VTOP_MCP_CONTAINER).
#
# Usage:  ./scripts/docker-login.sh [extra vtop-mcp login args...]

set -euo pipefail

CONTAINER="${VTOP_MCP_CONTAINER:-vtop-mcp}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CAP_DIR="$REPO_ROOT/.vtop-session/captcha"
CONTAINER_CAP_DIR="/app/.vtop-session/captcha"

mkdir -p "$CAP_DIR"
echo "Auto-opening new CAPTCHA images in: $CAP_DIR"

open_new_captcha() {
  while :; do
    local f size mtime now
    f="$(ls -t "$CAP_DIR"/vtop_captcha_* 2>/dev/null | head -n1 || true)"
    if [[ -n "$f" && -s "$f" ]]; then
      size="$(stat -c %s "$f")"
      mtime="$(stat -c %Y "$f")"
      now="$(date +%s)"
      if [[ "$size" -ge 32 && $((now - mtime)) -le 30 ]]; then
        echo "Opening CAPTCHA: $f"
        nohup xdg-open "$f" >/dev/null 2>&1 || echo "Could not auto-open; view it manually: $f"
        return 0
      fi
    fi
    sleep 0.3
  done
}

open_new_captcha &
WATCHER=$!
trap 'kill "$WATCHER" 2>/dev/null || true; rm -f "$CAP_DIR"/vtop_captcha_* 2>/dev/null || true' EXIT

docker exec -it "$CONTAINER" env TMPDIR="$CONTAINER_CAP_DIR" vtop-mcp login --no-open "$@"