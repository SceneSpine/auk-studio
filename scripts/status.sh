#!/usr/bin/env bash
# 查看进程、端口、模型与 worker 状态。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=== AuK Local Studio 状态 ==="
if [ -f logs/backend.pid ] && kill -0 "$(cat logs/backend.pid)" 2>/dev/null; then
  echo "后端: 运行中 (pid $(cat logs/backend.pid))"
else
  echo "后端: 未运行"
fi

if [ -f data/runtime.json ]; then
  PORT=$(.venv-auk/bin/python -c "import json;print(json.load(open('data/runtime.json'))['port'])" 2>/dev/null || echo "?")
  echo "地址: http://127.0.0.1:$PORT"
  curl -s --max-time 3 "http://127.0.0.1:$PORT/api/model/status" | .venv-auk/bin/python -c "
import json,sys
try:
    d=json.load(sys.stdin)
    w=d.get('worker',{})
    print(f\"模型: {d['variant']} | 下载={d['downloaded']} 转换={d['converted']} q8={d['quantized_q8']} 加载={d['loaded']}\")
    print(f\"Worker: pid={w.get('pid')} alive={w.get('alive')} MLX={w.get('mlx_version','?')} Metal={bool(w.get('metal_available'))}\")
    print(f\"当前任务: {w.get('current_job_id') or '空闲'}\")
except Exception as e:
    print('API 无响应:', e)
" 2>/dev/null || echo "API: 无响应"
fi

echo ""
echo "=== 磁盘 ==="
df -h "$ROOT" | awk 'NR==1||NR==2'
echo ""
echo "=== 内存压力 ==="
lvl=$(sysctl -n kern.memorystatus_vm_pressure_level 2>/dev/null || echo "?")
case "$lvl" in 1) echo "正常 (1)";; 2) echo "偏高 (2)";; 4) echo "严重 (4)";; *) echo "$lvl";; esac
echo ""
echo "=== 模型目录 ==="
du -sh models/* 2>/dev/null || true