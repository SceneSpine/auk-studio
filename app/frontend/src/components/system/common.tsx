/**
 * 环境检测共享件 — 就绪状态语义与数值格式化。
 * 状态双通道（文字+图标+颜色）；缺失数据一律「不可用」，绝不渲染假数字。
 */
import type { ReactNode } from "react";
import type { ReadinessLevel } from "../../types";
import { StatusBadge, type StatusTone } from "../ui";

export const READINESS_META: Record<ReadinessLevel, { tone: StatusTone; label: string; desc: string }> = {
  ready: { tone: "ready", label: "Ready · 已就绪", desc: "设备与资源满足本地推理要求，可以开始创作。" },
  caution: { tone: "warn", label: "Caution · 需注意", desc: "可以运行，但存在需要关注的风险项，建议先查看下方检查。" },
  blocked: { tone: "error", label: "Blocked · 受阻", desc: "存在阻断项，推理可能无法进行，请先按建议修复。" },
  unknown: { tone: "unknown", label: "Unknown · 未知", desc: "探针未能完成测量，请重新检测或查看技术细节。" },
};

/** GB 数值格式化；null/undefined/NaN → 不可用 */
export function fmtGb(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "不可用";
  return `${Number.isInteger(n) ? n : n.toFixed(1)} GB`;
}

/** 内存压力等级 → 语义（与后端 pressure_level 对齐：1 正常 / 2 偏高 / 4 严重 / 其余不可用） */
export function pressureMeta(level: number | null | undefined, label?: string): { tone: StatusTone; text: string } {
  if (level == null || level <= 0) return { tone: "unknown", text: label || "不可用" };
  if (level >= 4) return { tone: "error", text: label || "严重" };
  if (level >= 2) return { tone: "warn", text: label || "偏高" };
  return { tone: "ready", text: label || "正常" };
}

/** 顶部总体就绪状态大徽章 + 推断依据 */
export function ReadinessBanner({
  level,
  reasons,
  generatedAt,
  action,
}: {
  level: ReadinessLevel;
  reasons: string[];
  generatedAt?: string;
  action?: ReactNode;
}) {
  const meta = READINESS_META[level];
  return (
    <section className="rounded-panel border border-line bg-surface p-5" aria-label="总体就绪状态">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3.5">
          <StatusBadge tone={meta.tone} className="mt-0.5 px-3 py-1 text-sm">
            {meta.label}
          </StatusBadge>
          <div>
            <p className="text-sm leading-[22px] text-ink-2">{meta.desc}</p>
            {reasons.length > 0 && (
              <ul className="mt-2 space-y-1">
                {reasons.map((r, i) => (
                  <li key={i} className="flex items-start gap-1.5 text-[13px] leading-5 text-ink-2">
                    <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-ink-3" aria-hidden />
                    {r}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
        {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
      </div>
      {generatedAt && <p className="mt-3 border-t border-line pt-2.5 text-[11px] text-ink-3">最近检测：{generatedAt}</p>}
    </section>
  );
}