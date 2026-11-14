/**
 * 可折叠「技术细节」— platform 全字段 / memory（pressure/swap）/ disk（models/data 占用）/ paths。
 * paths 来自 system 接口；缺失显示「不可用」，工具未安装显示「未安装」。
 */
import type { ReactNode } from "react";
import { Collapse } from "../ui";
import type { Diagnostics, SystemInfo } from "../../types";
import { fmtGb } from "./common";

function Row({ label, value, mono = true }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[11px] leading-4 text-ink-3">{label}</dt>
      <dd className={mono ? "break-all font-mono text-[12.5px] leading-5 text-ink" : "text-[13px] leading-5 text-ink"}>{value}</dd>
    </div>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div>
      <h4 className="mb-2 text-[12px] font-semibold uppercase tracking-wider text-ink-3">{title}</h4>
      <dl className="grid grid-cols-1 gap-x-6 gap-y-2.5 sm:grid-cols-2 lg:grid-cols-3">{children}</dl>
    </div>
  );
}

const na = (v: string | null | undefined) => (v ? v : "不可用");
const tool = (v: string | null | undefined) => (v ? v : "未安装");

export function TechDetails({ diag, sys }: { diag: Diagnostics | null; sys: SystemInfo | null }) {
  return (
    <Collapse title="技术细节" badge={<span className="text-[11px] font-normal text-ink-3">platform · memory · disk · paths</span>}>
      <div className="space-y-5">
        <Group title="Platform">
          <Row label="芯片" value={na(diag?.platform.chip)} />
          <Row label="架构" value={na(diag?.platform.arch)} />
          <Row label="macOS" value={na(diag?.platform.macos)} />
          <Row label="Metal" value={diag ? (diag.platform.metal ? "可用" : "不可用") : "不可用"} mono={false} />
          <Row label="MLX 版本" value={tool(diag?.platform.mlx_version)} />
          <Row label="Python" value={na(diag?.platform.python)} />
          <Row label="uv" value={tool(diag?.platform.uv)} />
          <Row label="ffmpeg" value={tool(diag?.platform.ffmpeg)} />
          <Row label="git" value={tool(diag?.platform.git)} />
          <Row label="node" value={tool(diag?.platform.node)} />
        </Group>
        <Group title="Memory">
          <Row label="统一内存" value={fmtGb(diag?.memory.total_gb)} mono={false} />
          <Row label="压力等级" value={diag ? `${diag.memory.pressure_level}（${diag.memory.pressure_label}）` : "不可用"} mono={false} />
          <Row label="Swap 已用" value={fmtGb(diag?.memory.swap_used_gb)} mono={false} />
          <Row label="Swap 总量" value={fmtGb(diag?.memory.swap_total_gb)} mono={false} />
        </Group>
        <Group title="Disk">
          <Row label="总容量" value={fmtGb(diag?.disk.total_gb)} mono={false} />
          <Row label="剩余" value={fmtGb(diag?.disk.free_gb)} mono={false} />
          <Row label="模型占用" value={fmtGb(diag?.disk.models_gb)} mono={false} />
          <Row label="数据占用" value={fmtGb(diag?.disk.data_gb)} mono={false} />
        </Group>
        <Group title="Paths">
          <Row label="数据目录" value={na(sys?.paths.data)} />
          <Row label="模型目录" value={na(sys?.paths.models)} />
          <Row label="日志目录" value={na(sys?.paths.logs)} />
        </Group>
      </div>
    </Collapse>
  );
}