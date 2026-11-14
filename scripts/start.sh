#!/usr/bin/env bash
# 启动 AuK Studio（后端 + 内置前端构建）。端口占用时自动选择可用端口。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p logs

if [ -f logs/backend.pid ] && kill -0 "$(cat logs/backend.pid)" 2>/dev/null; then
  echo "✓ 已在运行 (pid $(cat logs/backend.pid))"
  cat data/runtime.json 2>/dev/null || true
  exit 0
fi

# 清理 stale runtime.json（进程已死时避免假就绪）
if [ -f data/runtime.json ]; then
  RPID=$(.venv-auk/bin/python -c "import json;print(json.load(open('data/runtime.json')).get('pid',''))" 2>/dev/null || echo "")
  if [ -n "$RPID" ] && ! kill -0 "$RPID" 2>/dev/null; then
    rm -f data/runtime.json
  fi
fi

# 前端构建（源码更新或缺失时；失败可见）
if [ ! -f app/frontend/dist/index.html ] || [ -n "$(find app/frontend/src app/frontend/index.html -newer app/frontend/dist/index.html 2>/dev/null | head -1)" ]; then
  echo "→ 构建前端…（日志 logs/frontend-build.log）"
  if ! (cd app/frontend && npm install --no-audit --no-fund && npm run build) > logs/frontend-build.log 2>&1; then
    echo "✗ 前端构建失败，最近日志："
    tail -25 logs/frontend-build.log
    exit 1
  fi
fi

echo "→ 启动后端…"
nohup .venv-auk/bin/python -m app.backend.main >> logs/backend.log 2>&1 &
echo $! > logs/backend.pid

# 等待就绪
for i in $(seq 1 30); do
  sleep 1
  if [ -f data/runtime.json ]; then
    PORT=$(.venv-auk/bin/python -c "import json;print(json.load(open('data/runtime.json'))['port'])" 2>/dev/null || echo "")
    if [ -n "$PORT" ] && curl -s --max-time 2 "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
      echo ""
      echo "  ✓ AuK Studio 已启动"
      echo "  Web 地址:  http://127.0.0.1:$PORT"
      echo "  API 地址:  http://127.0.0.1:$PORT/api"
      echo "  API 文档:  http://127.0.0.1:$PORT/docs"
      echo "  日志目录:  $ROOT/logs"
      echo "  数据目录:  $ROOT/data"
      curl -s --max-time 3 "http://127.0.0.1:$PORT/api/model/status" | .venv-auk/bin/python -c "
import json,sys
try:
    d=json.load(sys.stdin); w=d.get('worker',{})
    print(f\"  模型状态:  Flash={'就绪' if d['converted'] else '未转换'} Base={'就绪' if d.get('base_ready') else '未部署'} 已加载={d['loaded']}\")
    print(f\"  推理后端:  MLX {w.get('mlx_version','?')} / Metal={'可用' if w.get('metal_available') else '不可用'}\")
except Exception: pass" 2>/dev/null
      exit 0
    fi
  fi
done
echo "✗ 启动超时，查看 logs/backend.log"
tail -20 logs/backend.log
exit 1