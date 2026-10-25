#!/usr/bin/env bash
# 本地常驻启动 Bloom（idempotent：已在跑则只打印地址，不重复拉起）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PORT="${PORT:-8000}"
HOST="${HOST:-127.0.0.1}"
LOG="${ROOT}/.bloom-uvicorn.log"
PID_FILE="${ROOT}/.bloom-uvicorn.pid"

url_ok() {
  curl -fsS -m 2 "http://${HOST}:${PORT}/" >/dev/null 2>&1
}

if url_ok; then
  echo "Bloom 已在运行："
  echo "  作品首页    http://${HOST}:${PORT}/"
  echo "  双爆款合成  http://${HOST}:${PORT}/gap-fusion.html"
  echo "  趋势改造    http://${HOST}:${PORT}/design.html"
  exit 0
fi

# 清掉残留 PID（进程已死但文件还在）
if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${old_pid}" ]] && ! kill -0 "$old_pid" 2>/dev/null; then
    rm -f "$PID_FILE"
  fi
fi

cd "$ROOT"
# 优先用项目 venv（若有），否则系统 python3
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
elif [[ -x "$ROOT/venv/bin/python" ]]; then
  PY="$ROOT/venv/bin/python"
else
  PY="python3"
fi

echo "正在启动 Bloom → http://${HOST}:${PORT}/"
nohup "$PY" -m uvicorn app.main:app --host "$HOST" --port "$PORT" --reload \
  >"$LOG" 2>&1 &
echo $! >"$PID_FILE"

for _ in $(seq 1 30); do
  if url_ok; then
    echo "已启动（PID $(cat "$PID_FILE")），日志：$LOG"
    echo "  作品首页    http://${HOST}:${PORT}/"
    echo "  双爆款合成  http://${HOST}:${PORT}/gap-fusion.html"
    echo "  趋势改造    http://${HOST}:${PORT}/design.html"
    echo
    echo "停止：kill \$(cat \"$PID_FILE\")  或  scripts/stop-local.sh"
    exit 0
  fi
  sleep 0.5
done

echo "启动超时，请查看日志：$LOG" >&2
tail -n 40 "$LOG" >&2 || true
exit 1
