/**
 * 检查项列表 — 每项 图标+label+value+状态徽章；warn/fail 可展开 detail+suggestion+重试。
 * measured=false 标注「估计值」。状态不只靠颜色（StatusBadge 自带图标+文字）。
 */
import { useId, useState } from "react";
import {
  Activity, AudioLines, Boxes, ChevronDown, Cpu, Gauge, GitBranch, Globe,
  HardDrive, Laptop, MemoryStick, RefreshCw, Server, ShieldCheck, Terminal, Zap,
} from "lucide-react";
import type { DiagCheck, DiagStatus } from "../../types";
import { Button, StatusBadge, cn, type StatusTone } from "../ui";

type Icon = typeof Activity;

const STATUS_META: Record<DiagStatus, { tone: StatusTone; label: string }> = {
  ok: { tone: "ready", label: "正常" },
  warn: { tone: "warn", label: "注意" },
  fail: { tone: "error", label: "异常" },
  unknown: { tone: "unknown", label: "未知" },
};

function checkIcon(id: string): Icon {
  const s = id.toLowerCase();
  if (s.includes("arch") || s.includes("cpu") || s.includes("chip")) return Cpu;
  if (s.includes("macos") || s.includes("mac")) return Laptop;
  if (s.includes("metal")) return Zap;
  if (s.includes("mlx")) return Boxes;
  if (s.includes("swap")) return MemoryStick;
  if (s.includes("memory") || s.includes("pressure")) return Gauge;
  if (s.includes("disk")) return HardDrive;
  if (s.includes("ffmpeg") || s.includes("audio")) return AudioLines;
  if (s.includes("git")) return GitBranch;
  if (s.includes("network")) return Globe;
  if (s.includes("uv") || s.includes("python") || s.includes("node")) return Terminal;
  if (s.includes("worker")) return Server;
  if (s.includes("weight") || s.includes("model") || s.includes("integrity")) return ShieldCheck;
  return Activity;
}

function CheckRow({ check, onRetry }: { check: DiagCheck; onRetry?: () => void }) {
  const [open, setOpen] = useState(check.status === "fail");
  const panelId = useId();
  const meta = STATUS_META[check.status];
  const Icon = checkIcon(check.id);
  const expandable = check.status !== "ok";

  const head = (
    <>
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-input bg-subtle text-ink-2">
        <Icon size={16} aria-hidden />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
          <span className="text-[13.5px] font-medium text-ink">{check.label}</span>
          {!check.measured && (
            <span className="rounded-full bg-subtle px-1.5 py-px text-[10.5px] leading-4 text-ink-3">估计值</span>
          )}
        </span>
        <span className="block truncate text-xs leading-5 text-ink-2" title={check.value}>
          {check.value || "不可用"}
        </span>
      </span>
      <StatusBadge tone={meta.tone}>{meta.label}</StatusBadge>
      {expandable && (
        <ChevronDown size={15} className={cn("shrink-0 text-ink-3 transition-transform", open && "rotate-180")} aria-hidden />
      )}
    </>
  );

  return (
    <li>
      {expandable ? (
        <button
          type="button"
          className="flex w-full cursor-pointer items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-subtle/60"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          aria-controls={panelId}
        >
          {head}
        </button>
      ) : (
        <div className="flex items-center gap-3 px-4 py-3">{head}</div>
      )}
      {expandable && open && (
        <div id={panelId} className="space-y-2 border-t border-line bg-subtle/40 px-4 py-3">
          {check.detail && <p className="text-[13px] leading-5 text-ink-2">{check.detail}</p>}
          {check.suggestion && (
            <p className="text-[13px] leading-5 text-ink">
              <span className="font-medium">建议：</span>
              {check.suggestion}
            </p>
          )}
          {onRetry && (
            <Button size="sm" variant="secondary" icon={<RefreshCw size={13} />} onClick={onRetry}>
              重试
            </Button>
          )}
        </div>
      )}
    </li>
  );
}

export function CheckList({ checks, onRetry }: { checks: DiagCheck[]; onRetry?: () => void }) {
  if (checks.length === 0) {
    return <p className="rounded-panel border border-line bg-surface px-4 py-6 text-center text-[13px] text-ink-2">暂无检查项。</p>;
  }
  return (
    <ul className="divide-y divide-line overflow-hidden rounded-panel border border-line bg-surface" aria-label="环境检查项">
      {checks.map((c) => (
        <CheckRow key={c.id} check={c} onRetry={onRetry} />
      ))}
    </ul>
  );
}