#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-8000}"
PID_FILE="${ROOT}/.bloom-uvicorn.pid"

if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${pid}" ]] && kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    # --reload 会再起子进程，顺带清端口占用
    sleep 0.5
  fi
  rm -f "$PID_FILE"
fi

# 兜底：按端口杀监听（仅本机开发用）
if command -v lsof >/dev/null 2>&1; then
  pids="$(lsof -tiTCP:"$PORT" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "${pids}" ]]; then
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
  fi
fi

echo "Bloom 本地服务已停止（port ${PORT}）"
