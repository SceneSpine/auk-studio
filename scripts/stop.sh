#!/usr/bin/env bash
# 优雅停止后端与 worker（SIGINT → lifespan 关闭 → worker 释放模型退出）。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -f logs/backend.pid ]; then
  echo "未在运行（无 pid 文件）"
  exit 0
fi
PID=$(cat logs/backend.pid)
if ! kill -0 "$PID" 2>/dev/null; then
  echo "进程 $PID 不存在，清理 pid 文件"
  rm -f logs/backend.pid
  exit 0
fi

echo "→ 停止后端 (pid $PID)…"
kill -INT "$PID"
for i in $(seq 1 15); do
  kill -0 "$PID" 2>/dev/null || { echo "✓ 已停止"; rm -f logs/backend.pid; exit 0; }
  sleep 1
done
echo "→ 未在 15s 内退出，SIGTERM"
kill -TERM "$PID" 2>/dev/null || true
sleep 3
kill -0 "$PID" 2>/dev/null && kill -KILL "$PID" 2>/dev/null || true
rm -f logs/backend.pid
echo "✓ 已停止"