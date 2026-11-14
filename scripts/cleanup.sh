#!/usr/bin/env bash
# 清理临时文件与缓存。执行前列出将删除的内容并要求确认。
# 不会删除：上传原始音频、生成输出、数据库、模型权重。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "=== 将清理以下内容 ==="
TARGETS=()
[ -d data/temp ] && [ -n "$(ls -A data/temp 2>/dev/null)" ] && TARGETS+=("data/temp/*")
[ -d data/waveform-cache ] && [ -n "$(ls -A data/waveform-cache 2>/dev/null)" ] && TARGETS+=("data/waveform-cache/*（波形缓存，可再生）")
find models -name "*.part" -o -name "*.progress" 2>/dev/null | while read -r f; do echo "  未完成下载: $f"; done
PARTS=$(find models -name "*.part" -o -name "*.progress" 2>/dev/null)
[ -n "$PARTS" ] && TARGETS+=("models 中的 .part/.progress 残留")
for f in logs/*.log; do
  [ -f "$f" ] && [ "$(stat -f%z "$f" 2>/dev/null || echo 0)" -gt 10485760 ] && TARGETS+=("$f（>10MB，将截断）")
done

if [ ${#TARGETS[@]} -eq 0 ]; then
  echo "  （无可清理项）"
  exit 0
fi
printf '  %s\n' "${TARGETS[@]}"
echo ""
echo "保留: data/uploads data/outputs data/studio.db models/*.safetensors"
read -r -p "确认清理？[y/N] " ans
[ "$ans" = "y" ] || [ "$ans" = "Y" ] || { echo "已取消"; exit 0; }

rm -rf data/temp/* data/waveform-cache/*
find models -name "*.part" -delete 2>/dev/null || true
find models -name "*.progress" -delete 2>/dev/null || true
for f in logs/*.log; do
  [ -f "$f" ] && [ "$(stat -f%z "$f" 2>/dev/null || echo 0)" -gt 10485760 ] && : > "$f"
done
echo "✓ 清理完成"