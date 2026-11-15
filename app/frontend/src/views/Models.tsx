/**
 * 模型管理 — 本机摘要 + 模型行（状态/大小/许可/操作）+ 安装计划对话框 + 真实安装进度。
 * 卸载常驻模型（当前任务结束后释放）；不提供删除权重按钮（保护用户权重）。
 */
import { useEffect, useState } from "react";
import {
  Activity, ArrowRight, Cpu, ExternalLink, HardDrive, MemoryStick, Power, RefreshCw,
  ShieldCheck, Wand2, Zap,
} from "lucide-react";
import { api } from "../api";
import type { StudioMode, ViewKey } from "../components/AppShell";
import {
  Button, Card, ConfirmDialog, InlineError, InlineNote, PageHeader, Progress, Skeleton, StatusBadge, useToast,
} from "../components/ui";
import { fmtGb } from "../components/system/common";
import {
  MemoryFitBadge, ModelStateBadge, findModelJob, isBusyState,
} from "../components/models/common";
import { InstallPlanDialog } from "../components/models/InstallPlanDialog";
import { InstallProgress } from "../components/models/InstallProgress";
import ProviderManager from "../components/models/ProviderManager";
import { usePoll } from "../hooks";
import type { Diagnostics, Job, ModelInfo } from "../types";
import { RUNNING } from "../types";

function fitFromDiag(d: Diagnostics | null): ModelInfo["memory_fit"] {
  if (!d) return "unknown";
  if (d.platform.arch !== "arm64") return "unknown";
  const t = d.memory.total_gb;
  if (t >= 32) return "comfortable";
  if (t >= 16) return "tight";
  return "insufficient";
}

function SizeStat({ label, value }: { label: string; value: string }) {
  return (
    <span className="inline-flex flex-col">
      <span className="text-[10.5px] leading-4 text-ink-3">{label}</span>
      <span className="text-[12.5px] font-medium leading-5 text-ink">{value}</span>
    </span>
  );
}

export default function Models({ onNavigate }: { onNavigate: (v: ViewKey, m?: StudioMode) => void }) {
  const toast = useToast();
  const [modelsTick, setModelsTick] = useState(0);
  const [tracking, setTracking] = useState<string[]>([]);
  const [planModel, setPlanModel] = useState<ModelInfo | null>(null);
  const [unloadOpen, setUnloadOpen] = useState(false);
  const [unloadBusy, setUnloadBusy] = useState(false);
  const [busyMap, setBusyMap] = useState<Record<string, boolean>>({});
  const setBusy = (k: string, v: boolean) => setBusyMap((p) => ({ ...p, [k]: v }));

  const models = usePoll(api.models, 15000, true, [modelsTick]);
  const diag = usePoll(api.diagnostics, 30000, true);
  const sys = usePoll(api.system, 60000, true);

  const modelList = models.data?.models ?? [];
  const sorted = [...modelList].sort((a, b) => (a.role === b.role ? 0 : a.role === "main" ? -1 : 1));
  const anyBusy = modelList.some((m) => isBusyState(m.state));
  const jobs = usePoll(api.jobs, 2500, anyBusy || tracking.length > 0, [anyBusy, tracking.length]);
  const jobList = jobs.data ?? [];
  const worker = models.data?.worker;

  // 任务进入终态后停止对其的跟踪轮询
  useEffect(() => {
    const data = jobs.data;
    if (!data) return;
    setTracking((prev) => {
      const next = prev.filter((id) => {
        const j = data.find((x) => x.id === id);
        return j ? RUNNING.includes(j.status) : true;
      });
      return next.length === prev.length ? prev : next;
    });
  }, [jobs.data]);

  const track = (id: string) => setTracking((p) => (p.includes(id) ? p : [...p, id]));
  const bump = () => setModelsTick((t) => t + 1);

  const installJobFor = (m: ModelInfo): Job | null => {
    const found = findModelJob(jobList, m, "install");
    if (found) return found;
    const runningInstalls = jobList.filter((x) => x.kind === "install" && RUNNING.includes(x.status));
    const busyModels = modelList.filter((x) => isBusyState(x.state));
    if (runningInstalls.length === 1 && busyModels.length === 1 && busyModels[0].id === m.id) return runningInstalls[0];
    return null;
  };

  const activate = async (m: ModelInfo) => {
    setBusy(`use:${m.id}`, true);
    try {
      const res = await api.activateModel(m.id);
      toast("success", res.message || "已请求切换模型");
      bump();
    } catch (e) {
      toast("error", `切换失败：${(e as Error).message}`);
    } finally {
      setBusy(`use:${m.id}`, false);
    }
  };

  const verify = async (m: ModelInfo) => {
    setBusy(`verify:${m.id}`, true);
    try {
      const job = await api.verifyModel(m.id);
      track(job.id);
      toast("info", "校验任务已创建，正在核对权重哈希");
      bump();
    } catch (e) {
      toast("error", `校验失败：${(e as Error).message}`);
    } finally {
      setBusy(`verify:${m.id}`, false);
    }
  };

  const cancel = async (job: Job) => {
    setBusy(`cancel:${job.id}`, true);
    try {
      await api.cancelJob(job.id);
      toast("info", "已请求取消任务");
      bump();
    } catch (e) {
      toast("error", `取消失败：${(e as Error).message}`);
    } finally {
      setBusy(`cancel:${job.id}`, false);
    }
  };

  const retry = async (job: Job) => {
    setBusy(`retry:${job.id}`, true);
    try {
      const nj = await api.retryJob(job.id);
      track(nj.id);
      toast("info", "已重新提交任务");
      bump();
    } catch (e) {
      toast("error", `重试失败：${(e as Error).message}`);
    } finally {
      setBusy(`retry:${job.id}`, false);
    }
  };

  const unload = async () => {
    setUnloadBusy(true);
    try {
      const res = await api.unloadModel();
      toast("success", res.message || "已请求卸载常驻模型");
      setUnloadOpen(false);
      bump();
    } catch (e) {
      toast("error", `卸载失败：${(e as Error).message}`);
    } finally {
      setUnloadBusy(false);
    }
  };

  const fit = fitFromDiag(diag.data);

  return (
    <div className="space-y-5">
      <PageHeader
        title="模型管理"
        description="安装、校验与切换本地模型；已有权重将被复用，不会重复下载。本地 MLX 支持全部模式；配置远程 AuK 服务后，无需本地模型即可使用全部创作能力。"
        actions={
          <Button variant="outline" icon={<Wand2 size={15} />} onClick={() => onNavigate("wizard")}>
            安装向导
          </Button>
        }
      />

      {/* 本机摘要 */}
      <Card
        title="本机摘要"
        action={
          <Button size="sm" variant="ghost" icon={<Activity size={14} />} onClick={() => onNavigate("system")}>
            环境检测
          </Button>
        }
      >
        {diag.error && !diag.data && <InlineError onRetry={() => bump()}>本机摘要加载失败：{diag.error}</InlineError>}
        {!diag.data && !diag.error && <Skeleton className="h-10 w-full" />}
        {diag.data && (
          <div className="flex flex-wrap items-center gap-x-7 gap-y-3">
            <span className="flex items-center gap-2 text-[13px]">
              <Cpu size={16} className="text-ink-3" aria-hidden />
              <span className="font-medium">{diag.data.platform.chip || "不可用"}</span>
              <span className="text-ink-3">{diag.data.platform.arch}</span>
            </span>
            <span className="flex items-center gap-2 text-[13px]">
              <MemoryStick size={16} className="text-ink-3" aria-hidden />
              {fmtGb(diag.data.memory.total_gb)}
            </span>
            <span className="flex items-center gap-2 text-[13px]">
              <Zap size={16} className="text-ink-3" aria-hidden />
              <span className={diag.data.platform.metal ? "text-ok" : "text-err"}>
                {diag.data.platform.metal ? "Metal 可用" : "Metal 不可用"}
              </span>
            </span>
            <span className="flex items-center gap-2 text-[13px]">
              <HardDrive size={16} className="text-ink-3" aria-hidden />
              剩余 {fmtGb(diag.data.disk.free_gb)}
            </span>
            <span className="flex items-center gap-2 text-[13px]">
              适配等级 <MemoryFitBadge fit={fit} />
            </span>
            {worker?.model_loaded ? (
              <Button
                size="sm"
                variant="secondary"
                icon={<Power size={14} />}
                className="ml-auto"
                onClick={() => setUnloadOpen(true)}
              >
                卸载常驻模型
              </Button>
            ) : (
              <span className="ml-auto text-[12px] text-ink-3">当前无模型常驻</span>
            )}
          </div>
        )}
      </Card>

      {/* 推理 Provider（本地默认 + 远程 AuK） */}
      <Card title="推理 Provider">
        <ProviderManager />
      </Card>

      {/* 模型列表 */}
      {models.error && !models.data && (
        <InlineError onRetry={bump}>模型列表加载失败：{models.error}</InlineError>
      )}
      {!models.data && !models.error && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-48 w-full rounded-panel" />
          ))}
        </div>
      )}

      {models.data && (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          {sorted.map((m) => {
            const ij = installJobFor(m);
            const vj = findModelJob(jobList, m, "verify");
            const busy = isBusyState(m.state);
            const showInstallJob = ij && (busy || ij.status === "failed" || ij.status === "cancelled");
            return (
              <section key={m.id} className="rounded-panel border border-line bg-surface p-5" aria-label={m.display_name}>
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="text-[15px] font-semibold text-ink">{m.display_name}</h3>
                    <StatusBadge tone={m.role === "main" ? "progress" : "neutral"}>
                      {m.role === "main" ? "主模型" : "共用依赖"}
                    </StatusBadge>
                    {m.active && <StatusBadge tone="ready">常驻</StatusBadge>}
                  </div>
                  <ModelStateBadge state={m.state} />
                </div>

                <p className="mt-1.5 text-[13px] leading-5 text-ink-2">{m.description}</p>
                {m.state_detail && <p className="mt-1 text-[12px] leading-5 text-ink-3">{m.state_detail}</p>}

                {/* 大小 */}
                <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2 rounded-input bg-subtle/50 px-3.5 py-2.5">
                  <SizeStat label="下载" value={fmtGb(m.size.download_gb)} />
                  <SizeStat label="转换后" value={m.size.converted_gb > 0 ? fmtGb(m.size.converted_gb) : "—"} />
                  <SizeStat label="实际占用" value={m.size.disk_gb > 0 ? fmtGb(m.size.disk_gb) : "—"} />
                  <span className="ml-auto self-center">
                    <MemoryFitBadge fit={m.memory_fit} />
                  </span>
                </div>

                {/* 许可 */}
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <ShieldCheck size={14} className="text-ink-3" aria-hidden />
                  <span className="text-[12.5px] text-ink-2">{m.license.name}</span>
                  {m.license.commercial ? (
                    <StatusBadge tone="ready">可商用</StatusBadge>
                  ) : (
                    <StatusBadge tone="error">Research-only · 非商用</StatusBadge>
                  )}
                  {m.license.url && (
                    <a
                      href={m.license.url}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-0.5 text-[12px] font-medium text-brand hover:underline"
                    >
                      全文 <ExternalLink size={11} aria-hidden />
                    </a>
                  )}
                </div>
                {!m.license.commercial && (
                  <p className="mt-1 text-[12px] leading-5 text-warn">{m.license.summary}</p>
                )}

                {/* 进行中进度 */}
                {showInstallJob && (
                  <div className="mt-4 border-t border-line pt-4">
                    <InstallProgress
                      job={ij}
                      busy={!!busyMap[`cancel:${ij.id}`] || !!busyMap[`retry:${ij.id}`]}
                      onCancel={() => cancel(ij)}
                      onRetry={() => retry(ij)}
                    />
                  </div>
                )}
                {busy && !ij && (
                  <div className="mt-4 space-y-2 border-t border-line pt-4">
                    <StatusBadge tone="progress">正在处理</StatusBadge>
                    <Progress label="安装进度" />
                    <p className="text-[12px] text-ink-3">正在等待任务进度上报…</p>
                  </div>
                )}

                {/* 校验进度 */}
                {vj && RUNNING.includes(vj.status) && (
                  <div className="mt-4 border-t border-line pt-4">
                    <p className="mb-2 text-[12px] font-medium text-ink-2">权重校验</p>
                    <InstallProgress job={vj} busy={!!busyMap[`cancel:${vj.id}`]} onCancel={() => cancel(vj)} />
                  </div>
                )}

                {/* 操作 */}
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  {m.state === "ready" && m.role === "main" && (
                    <>
                      <Button
                        size="sm"
                        variant="primary"
                        icon={<ArrowRight size={14} />}
                        disabled={m.active}
                        loading={!!busyMap[`use:${m.id}`]}
                        onClick={() => activate(m)}
                      >
                        {m.active ? "当前常驻" : "使用"}
                      </Button>
                      <Button
                        size="sm"
                        icon={<ShieldCheck size={14} />}
                        loading={!!busyMap[`verify:${m.id}`]}
                        onClick={() => verify(m)}
                      >
                        校验
                      </Button>
                    </>
                  )}
                  {m.state === "ready" && m.role === "dependency" && (
                    <Button
                      size="sm"
                      icon={<ShieldCheck size={14} />}
                      loading={!!busyMap[`verify:${m.id}`]}
                      onClick={() => verify(m)}
                    >
                      校验
                    </Button>
                  )}
                  {(m.state === "not_installed" || m.state === "broken" || m.state === "awaiting_license") && (
                    <Button size="sm" variant="primary" icon={<RefreshCw size={14} />} onClick={() => setPlanModel(m)}>
                      查看安装计划
                    </Button>
                  )}
                  {m.state === "incompatible" && (
                    <span className="text-[12.5px] text-err">该模型与本机环境不兼容，暂不可安装。</span>
                  )}
                  <span className="ml-auto truncate font-mono text-[11px] text-ink-3" title={`${m.source.repo} @ ${m.source.revision}`}>
                    {m.source.repo}
                  </span>
                </div>
              </section>
            );
          })}
        </div>
      )}

      {/* 权重保护说明 */}
      <InlineNote>
        为保护你的数据，本页不提供删除权重按钮。原始权重与转换产物位于
        <span className="mx-1 font-mono">{sys.data?.paths.models ?? "models/ 目录"}</span>
        ，如需清理请在文件系统中手动确认后进行。卸载常驻模型只释放内存，不会删除任何文件。
      </InlineNote>

      <InstallPlanDialog
        model={planModel}
        onClose={() => setPlanModel(null)}
        onStarted={(job) => {
          track(job.id);
          toast("success", "安装任务已创建，可在模型卡片查看进度");
          bump();
        }}
      />

      <ConfirmDialog
        open={unloadOpen}
        onClose={() => setUnloadOpen(false)}
        onConfirm={unload}
        title="卸载常驻模型"
        confirmLabel="卸载"
        loading={unloadBusy}
      >
        将释放当前加载的模型所占用的内存。若有任务正在运行，会在当前任务结束后释放；不会删除任何权重文件，下次使用时重新加载。
      </ConfirmDialog>
    </div>
  );
}