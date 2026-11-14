/**
 * 概览 — 资源摘要横栏 + 快捷创作 + 已安装模型 + 最近任务 + 首次安装引导。
 * 真实 API：jobs 8s / models 15s / diagnostics 30s（失败回退 system）。缺失显示「不可用」。
 */
import { useState } from "react";
import {
  ArrowRight, AudioWaveform, History, Mic, Package, Palette, Plus, Rocket, Sparkles,
} from "lucide-react";
import { api } from "../api";
import type { StudioMode, ViewKey } from "../components/AppShell";
import {
  Button, Card, EmptyState, InlineError, InlineNote, PageHeader, Skeleton, StatusBadge, cn, type StatusTone,
} from "../components/ui";
import { ResourceBar } from "../components/system/ResourceBar";
import { fmtGb } from "../components/system/common";
import { ModelStateBadge, isBusyState } from "../components/models/common";
import { usePoll } from "../hooks";
import type { Job, JobStatus } from "../types";
import { MODE_LABEL, STATUS_LABEL, fmtAgo, fmtDur } from "../types";

const JOB_TONE: Record<JobStatus, StatusTone> = {
  queued: "neutral",
  preparing: "progress",
  loading_model: "progress",
  processing: "progress",
  postprocessing: "progress",
  completed: "ready",
  failed: "error",
  cancelled: "unknown",
};

const QUICK = [
  { key: "edit", title: "台词编辑", desc: "替换原对白，保留原始表演", icon: AudioWaveform, view: "studio" as ViewKey, mode: "edit" as StudioMode },
  { key: "tts", title: "文本转语音", desc: "从文字到声音，零样本克隆", icon: Mic, view: "studio" as ViewKey, mode: "tts" as StudioMode },
  { key: "design", title: "音色设计", desc: "用一段描述创造音色", icon: Sparkles, view: "studio" as ViewKey, mode: "design" as StudioMode },
  { key: "voices", title: "克隆音色", desc: "管理已授权的参考音色", icon: Palette, view: "voices" as ViewKey, mode: undefined },
];

function variantLabel(v: string): string {
  if (v === "flash") return "Flash";
  if (v === "base") return "Base";
  return v || "—";
}

export default function Dashboard({ onNavigate }: { onNavigate: (v: ViewKey, m?: StudioMode) => void }) {
  const [diagTick, setDiagTick] = useState(0);
  const [modelsTick, setModelsTick] = useState(0);
  const [jobsTick, setJobsTick] = useState(0);

  const diag = usePoll(api.diagnostics, 30000, true, [diagTick]);
  const sys = usePoll(api.system, 30000, !!diag.error, [diagTick]);
  const models = usePoll(api.models, 15000, true, [modelsTick]);
  const jobs = usePoll(api.jobs, 8000, true, [jobsTick]);

  const modelList = models.data?.models ?? [];
  const mains = modelList.filter((m) => m.role === "main");
  const deps = modelList.filter((m) => m.role === "dependency");
  const noneReady = mains.length > 0 && !mains.some((m) => m.state === "ready" || isBusyState(m.state));
  const depsReady = deps.length > 0 && deps.every((m) => m.state === "ready");

  const recent: Job[] = [...(jobs.data ?? [])]
    .filter((j) => j.kind === "infer")
    .sort((a, b) => b.created_at - a.created_at)
    .slice(0, 6);

  return (
    <div className="space-y-6">
      <PageHeader
        title="你好，开始创作吧"
        description="所有语音处理都在你的设备上完成"
        actions={
          <Button variant="primary" icon={<Plus size={16} />} onClick={() => onNavigate("studio", "edit")}>
            新建任务
          </Button>
        }
      />

      {/* 首次安装引导 */}
      {models.data && noneReady && (
        <section className="auk-fade-in rounded-panel border border-brand/30 bg-brand-tint p-5" aria-label="首次安装引导">
          <div className="flex flex-wrap items-start justify-between gap-4">
            <div className="flex items-start gap-3.5">
              <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-input bg-brand text-white">
                <Rocket size={20} aria-hidden />
              </span>
              <div>
                <h2 className="text-[15px] font-semibold text-ink">还差一步，即可开始本地创作</h2>
                <p className="mt-1 max-w-xl text-[13px] leading-5 text-ink-2">
                  {depsReady
                    ? "共享依赖已就绪，还差主模型的下载与转换。"
                    : "尚未安装任何模型权重。需要依次完成：环境检测 → 选择模型 → 确认许可 → 下载转换 → 验证。"}
                </p>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Button variant="ghost" onClick={() => onNavigate("system")}>环境检测</Button>
              <Button variant="primary" icon={<ArrowRight size={15} />} onClick={() => onNavigate("wizard")}>
                开始安装向导
              </Button>
            </div>
          </div>
        </section>
      )}

      {/* 资源摘要横栏 */}
      <div className="space-y-2">
        <ResourceBar
          diag={diag.data}
          sys={sys.data}
          loading={!diag.data && !sys.data && !diag.error}
          onDetail={() => onNavigate("system")}
        />
        {diag.error && sys.error && (
          <InlineError onRetry={() => setDiagTick((t) => t + 1)}>资源检测失败：{diag.error}</InlineError>
        )}
      </div>

      {/* 快捷创作 */}
      <section aria-label="快捷创作">
        <h2 className="mb-3 text-base font-semibold leading-6">快捷创作</h2>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {QUICK.map((q) => {
            const Icon = q.icon;
            return (
              <button
                key={q.key}
                onClick={() => onNavigate(q.view, q.mode)}
                className="group flex cursor-pointer items-start gap-3 rounded-panel border border-line bg-surface p-4 text-left transition-colors hover:border-brand/40 hover:bg-subtle/60"
              >
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-input bg-brand-tint text-brand transition-colors group-hover:bg-brand group-hover:text-white">
                  <Icon size={19} aria-hidden />
                </span>
                <span className="min-w-0">
                  <span className="flex items-center gap-1 text-[14px] font-semibold text-ink">
                    {q.title}
                    <ArrowRight size={14} className="text-ink-3 opacity-0 transition-opacity group-hover:opacity-100" aria-hidden />
                  </span>
                  <span className="mt-0.5 block text-[12.5px] leading-5 text-ink-2">{q.desc}</span>
                </span>
              </button>
            );
          })}
        </div>
      </section>

      {/* 模型 + 最近任务 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        {/* 已安装模型 */}
        <Card
          className="lg:col-span-2"
          title="模型"
          action={
            <Button size="sm" variant="ghost" icon={<Package size={14} />} onClick={() => onNavigate("models")}>
              管理模型
            </Button>
          }
        >
          {models.error && !models.data && (
            <InlineError onRetry={() => setModelsTick((t) => t + 1)}>模型状态加载失败：{models.error}</InlineError>
          )}
          {!models.data && !models.error && (
            <div className="space-y-3">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          )}
          {models.data && (
            <div className="space-y-3">
              {mains.map((m) => (
                <div key={m.id} className="flex items-center justify-between gap-3 rounded-input border border-line px-3.5 py-2.5">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-[13.5px] font-medium text-ink">{m.display_name}</span>
                      {m.active && <StatusBadge tone="progress">常驻</StatusBadge>}
                    </div>
                    <span className="text-[11.5px] text-ink-3">
                      {m.state === "ready" ? `占用 ${fmtGb(m.size.disk_gb)}` : `预计下载 ${fmtGb(m.size.download_gb)}`}
                    </span>
                  </div>
                  <ModelStateBadge state={m.state} />
                </div>
              ))}
              {deps.length > 0 && (
                <p className="text-[12px] leading-5 text-ink-3">
                  共用依赖：
                  {deps.map((d, i) => (
                    <span key={d.id}>
                      {i > 0 && " · "}
                      {d.display_name}
                      <span className={cn("ml-1", d.state === "ready" ? "text-ok" : "text-ink-3")}>
                        {d.state === "ready" ? "已就绪" : "需安装"}
                      </span>
                    </span>
                  ))}
                </p>
              )}
              {noneReady && !depsReady && (
                <InlineNote>主模型尚未就绪，可运行安装向导完成下载与转换。</InlineNote>
              )}
            </div>
          )}
        </Card>

        {/* 最近任务 */}
        <Card
          className="lg:col-span-3"
          title="最近任务"
          action={
            <Button size="sm" variant="ghost" icon={<History size={14} />} onClick={() => onNavigate("jobs")}>
              查看全部
            </Button>
          }
          padded={false}
        >
          {jobs.error && !jobs.data && (
            <div className="p-5">
              <InlineError onRetry={() => setJobsTick((t) => t + 1)}>任务加载失败：{jobs.error}</InlineError>
            </div>
          )}
          {!jobs.data && !jobs.error && (
            <div className="space-y-2 p-5">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="h-9 w-full" />
              ))}
            </div>
          )}
          {jobs.data && recent.length === 0 && (
            <EmptyState
              icon={<History size={24} />}
              title="还没有创作任务"
              description="从一段录音或一句文字开始你的第一次本地创作。"
              action={
                <Button variant="primary" size="sm" icon={<Plus size={14} />} onClick={() => onNavigate("studio", "edit")}>
                  新建任务
                </Button>
              }
            />
          )}
          {jobs.data && recent.length > 0 && (
            <ul className="divide-y divide-line">
              {recent.map((j) => (
                <li key={j.id}>
                  <button
                    onClick={() => onNavigate("jobs")}
                    className="flex w-full cursor-pointer items-center gap-3 px-5 py-3 text-left transition-colors hover:bg-subtle/60"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13.5px] font-medium text-ink">
                        {j.audio?.original_name || j.target_text || j.description || `任务 ${j.id.slice(0, 6)}`}
                      </span>
                      <span className="block text-[11.5px] text-ink-3">
                        {MODE_LABEL[j.mode]} · {variantLabel(j.model_variant)}
                        <span className="sm:hidden"> · {fmtAgo(j.finished_at ?? j.created_at)}</span>
                      </span>
                    </span>
                    <span className="hidden text-[12px] text-ink-3 sm:inline">{fmtAgo(j.finished_at ?? j.created_at)}</span>
                    <span className="hidden text-[12px] text-ink-3 xl:inline">{fmtDur(j.elapsed_s)}</span>
                    <StatusBadge tone={JOB_TONE[j.status]}>{STATUS_LABEL[j.status]}</StatusBadge>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}