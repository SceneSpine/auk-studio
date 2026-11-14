#!/usr/bin/env bash
# 备份配置、数据库与工程元数据（默认不含模型权重与大音频）。
# --with-audio  同时备份上传与输出音频
# --with-models 同时备份模型权重（体积大，谨慎）
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
STAMP=$(date +%Y%m%d-%H%M%S)
OUT="$ROOT/backups"
mkdir -p "$OUT"
DEST="$OUT/auk-studio-$STAMP.tar.gz"

ITEMS=(config data/jobs logs scripts .env.example README.md docs)
[ -f .env ] && ITEMS+=(.env)
if [ "${1:-}" = "--with-audio" ] || [ "${2:-}" = "--with-audio" ]; then
  ITEMS+=(data/uploads data/outputs)
fi
if [ "${1:-}" = "--with-models" ] || [ "${2:-}" = "--with-models" ]; then
  ITEMS+=(models)
fi

# SQLite 一致性备份（WAL 活动库直接 tar 有一致性风险）
STAGE="$OUT/.stage-$STAMP"
mkdir -p "$STAGE/data"
if [ -f data/studio.db ]; then
  if command -v sqlite3 >/dev/null; then
    sqlite3 data/studio.db ".backup '$STAGE/data/studio.db'"
  else
    .venv-auk/bin/python -c "import sqlite3; s=sqlite3.connect('data/studio.db'); d=sqlite3.connect('$STAGE/data/studio.db'); s.backup(d); d.close(); s.close()"
  fi
  ITEMS+=("$STAGE/data/studio.db")
fi

echo "→ 备份内容: ${ITEMS[*]}"
tar czf "$DEST" "${ITEMS[@]}"
rm -rf "$STAGE"
echo "✓ 备份完成: $DEST ($(du -h "$DEST" | cut -f1))"