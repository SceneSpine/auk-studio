/**
 * 资源摘要横栏（概览页）— 一条横栏而非 KPI 卡片堆叠。
 * 数据优先 diagnostics，失败回退 system；缺失字段显示「不可用」，绝不渲染假数字。
 */
import type { ReactNode } from "react";
import { ArrowRight, Cpu, Gauge, HardDrive, MemoryStick, Zap } from "lucide-react";
import type { Diagnostics, SystemInfo } from "../../types";
import { Button, Skeleton, StatusBadge } from "../ui";
import { fmtGb, pressureMeta } from "./common";

function Item({ icon, label, children }: { icon: ReactNode; label: string; children: ReactNode }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="text-ink-3" aria-hidden>{icon}</span>
      <span className="min-w-0">
        <span className="block text-[11px] leading-4 text-ink-3">{label}</span>
        <span className="block text-[13px] font-medium leading-5 text-ink">{children}</span>
      </span>
    </div>
  );
}

export function ResourceBar({
  diag,
  sys,
  loading,
  onDetail,
}: {
  diag: Diagnostics | null;
  sys: SystemInfo | null;
  loading: boolean;
  onDetail: () => void;
}) {
  if (loading) {
    return (
      <div className="flex flex-wrap items-center gap-x-8 gap-y-3 rounded-panel border border-line bg-surface px-5 py-4">
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-28" />
        ))}
      </div>
    );
  }

  const chip = diag
    ? `${diag.platform.chip || "不可用"} · ${diag.platform.arch || "不可用"}`
    : sys
      ? `${sys.platform.processor || "不可用"} · ${sys.platform.machine || "不可用"}`
      : "不可用";

  const memTotal = diag?.memory.total_gb ?? sys?.memory.total_gb;
  const pressure = pressureMeta(diag?.memory.pressure_level ?? sys?.memory.pressure_level, diag?.memory.pressure_label);
  const diskFree = diag?.disk.free_gb ?? sys?.disk.free_gb;

  const mlx = diag
    ? diag.platform.mlx_version
      ? `MLX ${diag.platform.mlx_version}`
      : "MLX 不可用"
    : sys
      ? sys.inference_backend || "不可用"
      : "不可用";
  const metal = diag ? diag.platform.metal : sys ? !!sys.worker.metal_available : null;

  return (
    <div className="flex flex-wrap items-center gap-x-7 gap-y-3 rounded-panel border border-line bg-surface px-5 py-3.5">
      <Item icon={<Cpu size={17} />} label="芯片 / 架构">{chip}</Item>
      <Item icon={<MemoryStick size={17} />} label="统一内存">{fmtGb(memTotal)}</Item>
      <Item icon={<Gauge size={17} />} label="内存压力">
        {diag || sys ? <StatusBadge tone={pressure.tone}>{pressure.text}</StatusBadge> : "不可用"}
      </Item>
      <Item icon={<HardDrive size={17} />} label="磁盘剩余">{fmtGb(diskFree)}</Item>
      <Item icon={<Zap size={17} />} label="MLX / Metal">
        {diag || sys ? (
          <span className="inline-flex items-center gap-1.5">
            {mlx}
            <span className="text-ink-3" aria-hidden>·</span>
            <span className={metal ? "text-ok" : "text-err"}>{metal == null ? "不可用" : metal ? "Metal 可用" : "Metal 不可用"}</span>
          </span>
        ) : (
          "不可用"
        )}
      </Item>
      <div className="ml-auto">
        <Button size="sm" variant="ghost" icon={<ArrowRight size={14} />} onClick={onDetail}>
          详细检测
        </Button>
      </div>
    </div>
  );
}