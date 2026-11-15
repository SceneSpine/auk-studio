/**
 * 任务详情弹窗：参数全量 / 阶段时间线 / 安装进度 / 日志轮询 / 结果试听下载 /
 * 取消·重试·删除（二次确认）·标记接受。
 */
import { useEffect, useState, type ReactNode } from "react";
import { AudioWaveform, Ban, Check, FileAudio, RotateCcw, ScrollText, Trash2 } from "lucide-react";
import { api } from "../../api";
import { usePoll } from "../../hooks";
import type { FileRef, Job, JobStatus } from "../../types";
import { RUNNING, STATUS_LABEL, fmtBytes, fmtDur, fmtTime } from "../../types";
import type { StudioMode, ViewKey } from "../AppShell";
import {
  Button,
  ConfirmDialog,
  Dialog,
  DownloadLink,
  InlineError,
  InlineNote,
  Progress,
  Skeleton,
  StatusBadge,
  Stepper,
  useToast,
} from "../ui";
import JobLog from "./JobLog";
import { INSTALL_PHASE_LABEL, jobKind, kindLabel, modelLabel, statusTone } from "./shared";
import { ProviderBadge, useProviderMap } from "../models/ProviderBadge";
import { isOnlineProvider } from "../studio/shared";

const INFER_STAGES: { key: JobStatus; label: string }[] = [
  { key: "queued", label: "排队" },
  { key: "preparing", label: "准备" },
  { key: "loading_model", label: "加载模型" },
  { key: "processing", label: "推理" },
  { key: "postprocessing", label: "后处理" },
  { key: "completed", label: "完成" },
];

const INSTALL_PHASES = ["prepare", "download", "verify", "convert", "quantize", "smoke", "done"];

/* ---------------- 阶段时间线 ---------------- */

function TerminalEvents({ job }: { job: Job }) {
  const failed = job.status === "failed";
  const events: { label: string; time: string; tone: "ok" | "err" | "idle" }[] = [
    { label: "创建", time: fmtTime(job.created_at), tone: "ok" },
    { label: "开始", time: job.started_at ? fmtTime(job.started_at) : "未开始", tone: job.started_at ? "ok" : "idle" },
    { label: failed ? "失败" : "取消", time: fmtTime(job.finished_at), tone: failed ? "err" : "idle" },
  ];
  return (
    <div className="space-y-2">
      <ol className="space-y-2">
        {events.map((ev) => (
          <li key={ev.label} className="flex items-center gap-2.5 text-[13px]">
            <span
              aria-hidden
              className={
                "inline-block h-2 w-2 shrink-0 rounded-full " +
                (ev.tone === "ok" ? "bg-ok" : ev.tone === "err" ? "bg-err" : "bg-ink-3")
              }
            />
            <span className="w-12 shrink-0 text-ink-3">{ev.label}</span>
            <span className="text-ink-2">{ev.time}</span>
          </li>
        ))}
      </ol>
      {job.stage_detail && <p className="text-xs leading-[18px] text-ink-3">停止时阶段：{job.stage_detail}</p>}
    </div>
  );
}

function StageTimeline({ job }: { job: Job }) {
  const kind = jobKind(job);
  const running = RUNNING.includes(job.status);

  if (job.status === "failed" || job.status === "cancelled") return <TerminalEvents job={job} />;

  if (kind === "infer") {
    const idx = INFER_STAGES.findIndex((s) => s.key === job.status);
    if (idx < 0) return <p className="text-xs text-ink-3">阶段信息不可用</p>;
    const done = job.status === "completed" ? INFER_STAGES.map((_, i) => i) : INFER_STAGES.slice(0, idx).map((_, i) => i);
    return (
      <div className="space-y-2">
        <Stepper steps={INFER_STAGES.map((s) => s.label)} current={idx} done={done} />
        {running && job.stage_detail && <p className="text-xs leading-[18px] text-ink-3">当前阶段：{job.stage_detail}</p>}
      </div>
    );
  }

  /* install / verify：按 install_json.phase 展示 */
  const phase = job.install_json?.phase;
  if (!phase) return <p className="text-xs text-ink-3">暂无阶段信息（等待 worker 上报进度）</p>;
  const idx = INSTALL_PHASES.indexOf(phase);
  const allDone = job.status === "completed" || phase === "done";
  const done = allDone ? INSTALL_PHASES.map((_, i) => i) : INSTALL_PHASES.slice(0, Math.max(0, idx)).map((_, i) => i);
  return (
    <div className="space-y-2">
      <Stepper steps={INSTALL_PHASES.map((p) => INSTALL_PHASE_LABEL[p] ?? p)} current={Math.max(0, idx)} done={done} />
      {running && job.stage_detail && <p className="text-xs leading-[18px] text-ink-3">当前阶段：{job.stage_detail}</p>}
    </div>
  );
}

/* ---------------- 安装/校验进度 ---------------- */

function InstallProgress({ job }: { job: Job }) {
  const ij = job.install_json;
  if (!ij) return null;
  const running = RUNNING.includes(job.status);
  const hasBytes = ij.phase === "download" && ij.total_bytes != null && ij.total_bytes > 0;
  const pct = hasBytes ? Math.min(100, ((ij.downloaded_bytes ?? 0) / (ij.total_bytes ?? 1)) * 100) : null;
  return (
    <div className="space-y-2 rounded-input border border-line bg-subtle/50 p-3.5">
      <div className="flex flex-wrap items-center gap-2">
        <StatusBadge tone={job.status === "completed" ? "ready" : running ? "progress" : "neutral"}>
          {INSTALL_PHASE_LABEL[ij.phase] ?? ij.phase}
        </StatusBadge>
        {ij.files_total != null && ij.files_total > 0 && (
          <span className="text-xs text-ink-2">
            文件 {ij.files_done ?? 0}/{ij.files_total}
          </span>
        )}
      </div>
      <Progress value={pct} label="安装进度" />
      <p className="text-xs leading-[18px] text-ink-2">
        {hasBytes
          ? `${fmtBytes(ij.downloaded_bytes ?? 0)} / ${fmtBytes(ij.total_bytes ?? 0)}（${(pct ?? 0).toFixed(0)}%）`
          : "该阶段无精确百分比，显示不确定进度（不伪造数值）"}
      </p>
      {ij.detail && <p className="break-all text-xs leading-[18px] text-ink-3">{ij.detail}</p>}
    </div>
  );
}

/* ---------------- 参数 ---------------- */

function ParamGrid({ job, providerName }: { job: Job; providerName?: string | null }) {
  const kind = jobKind(job);
  const online = isOnlineProvider(job.provider_id);
  const acceptItem = { label: "接受状态", value: job.accepted === 1 ? "已接受" : job.accepted === 0 ? "不接受" : "未评价" };
  const items: { label: string; value: ReactNode }[] =
    kind === "infer"
      ? [
          // 远程 AuK：参数转发远程生效，与本地参数一并展示（RTF/峰值内存为远程任务时为空）
          ...(online ? [{ label: "推理 Provider", value: providerName ?? "远程 AuK" }] : []),
          { label: "模型", value: modelLabel(job.model_variant) },
          { label: "精度", value: job.bits ? `${job.bits}-bit` : "fp32" },
          { label: "Sequential", value: job.sequential ? "开" : "关" },
          { label: "种子", value: job.seed != null ? String(job.seed) : "随机" },
          { label: "目标时长", value: job.gen_seconds != null ? `${job.gen_seconds}s` : "自动" },
          { label: "NFE 步数", value: job.nfe != null ? String(job.nfe) : "默认" },
          { label: "峰值内存", value: job.peak_memory_gb != null ? `${job.peak_memory_gb} GB` : "—" },
          { label: "RTF", value: job.rtf != null ? job.rtf.toFixed(2) : "—" },
          { label: "输出时长", value: fmtDur(job.output_duration) },
          acceptItem,
        ]
      : [{ label: "目标模型", value: modelLabel(job.model_variant) }];
  if (kind === "infer" && job.voice_id) items.push({ label: "引用音色", value: job.voice_id });

  const texts: { label: string; value: string }[] = [];
  if (kind === "infer") {
    if (job.segment?.original || job.segment?.replacement) {
      texts.push({ label: "片段替换", value: `${job.segment?.original ?? ""} → ${job.segment?.replacement ?? ""}` });
    }
    if (job.original_text) texts.push({ label: "原始全文", value: job.original_text });
    if (job.target_text) texts.push({ label: "目标文本", value: job.target_text });
    if (job.description) texts.push({ label: "音色/风格描述", value: job.description });
    if (job.emotion) texts.push({ label: "目标情绪", value: job.emotion });
    if (job.instruction && job.instruction !== job.final_instruction) texts.push({ label: "用户指令", value: job.instruction });
  }

  return (
    <div className="space-y-3">
      <dl className="grid grid-cols-2 gap-x-5 gap-y-2 text-[13px] sm:grid-cols-3">
        {items.map((it) => (
          <div key={it.label}>
            <dt className="text-xs text-ink-3">{it.label}</dt>
            <dd className="mt-0.5 font-medium">{it.value}</dd>
          </div>
        ))}
      </dl>
      {kind === "infer" && (
        <div>
          <div className="mb-1 text-xs text-ink-3">最终指令（final_instruction）</div>
          <p className="whitespace-pre-wrap break-words rounded-input bg-subtle px-3 py-2 font-mono text-xs leading-5 text-ink-2">
            {job.final_instruction || "—"}
          </p>
        </div>
      )}
      {texts.map((t) => (
        <div key={t.label}>
          <div className="mb-1 text-xs text-ink-3">{t.label}</div>
          <p className="whitespace-pre-wrap break-words rounded-input bg-subtle px-3 py-2 text-xs leading-5 text-ink-2">{t.value}</p>
        </div>
      ))}
    </div>
  );
}

/* ---------------- 结果文件 ---------------- */

function OutputFiles({ files }: { files: FileRef[] }) {
  const outputs = files.filter((f) => f.kind !== "upload" && f.exists !== false);
  if (outputs.length === 0) return <p className="text-[13px] text-ink-3">暂无输出文件</p>;
  return (
    <div className="space-y-2.5">
      {outputs.map((f) => (
        <div key={f.id} className="rounded-input border border-line p-3">
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="flex min-w-0 items-center gap-1.5 text-[13px] font-medium">
              <FileAudio size={14} className="shrink-0 text-ink-3" aria-hidden />
              <span className="truncate">{f.label || f.kind}</span>
            </span>
            <DownloadLink href={api.fileUrl(f.id, true)}>下载</DownloadLink>
          </div>
          <audio controls preload="none" src={api.fileUrl(f.id)} className="h-9 w-full" aria-label={`试听 ${f.label || f.kind}`} />
          {(f.duration != null || f.sample_rate != null) && (
            <div className="mt-1 text-[11px] text-ink-3">
              {f.duration != null ? fmtDur(f.duration) : ""}
              {f.sample_rate != null ? ` · ${f.sample_rate} Hz` : ""}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

/* ---------------- 主组件 ---------------- */

export default function JobDetail({
  jobId,
  onClose,
  onChanged,
  onOpenJob,
  onNavigate,
}: {
  jobId: string;
  onClose: () => void;
  /** 通知列表刷新 */
  onChanged: () => void;
  /** 重试后打开新任务 */
  onOpenJob: (id: string) => void;
  onNavigate: (v: ViewKey, m?: StudioMode) => void;
}) {
  const toast = useToast();
  const [tick, setTick] = useState(0);
  const [busy, setBusy] = useState<"cancel" | "retry" | "accept" | "delete" | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const providerMap = useProviderMap();

  /* 运行中 2.5s 轮询；终态降频到 60s（首次仍立即拉取） */
  const [pollMs, setPollMs] = useState(2500);
  const { data, error } = usePoll(() => api.jobResult(jobId), pollMs, true, [jobId, tick]);
  const j = data?.job ?? null;
  const files = data?.files ?? [];
  const inputAudio = data?.audio ?? null;

  useEffect(() => {
    setPollMs(j && !RUNNING.includes(j.status) ? 60000 : 2500);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [j?.status]);

  const refresh = () => {
    setTick((t) => t + 1);
    onChanged();
  };

  /* 删除确认打开时，Esc 只关闭确认层（捕获阶段拦截，避免连带关闭详情） */
  useEffect(() => {
    if (!confirmDelete) return;
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setConfirmDelete(false);
      }
    };
    document.addEventListener("keydown", h, true);
    return () => document.removeEventListener("keydown", h, true);
  }, [confirmDelete]);

  const doCancel = async () => {
    setBusy("cancel");
    try {
      const r = await api.cancelJob(jobId);
      toast("info", r.message ?? "已请求取消：任务将在阶段边界停止，不会立即中断。");
      refresh();
    } catch (e) {
      toast("error", `取消失败：${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  const doRetry = async () => {
    setBusy("retry");
    try {
      const nj = await api.retryJob(jobId);
      toast("success", "已重新提交任务");
      onChanged();
      onOpenJob(nj.id);
    } catch (e) {
      toast("error", `重试失败：${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  const doAccept = async () => {
    if (!j) return;
    setBusy("accept");
    try {
      const next = j.accepted === 1 ? null : true;
      await api.acceptJob(jobId, next);
      toast("success", next ? "已标记接受该结果" : "已取消接受标记");
      refresh();
    } catch (e) {
      toast("error", `操作失败：${(e as Error).message}`);
    } finally {
      setBusy(null);
    }
  };

  const doDelete = async () => {
    setBusy("delete");
    try {
      await api.deleteJob(jobId);
      toast("success", "任务已删除，输出文件已一并清理");
      onChanged();
      onClose();
    } catch (e) {
      toast("error", `删除失败：${(e as Error).message}`);
    } finally {
      setBusy(null);
      setConfirmDelete(false);
    }
  };

  const kind = j ? jobKind(j) : "infer";
  const terminal = j ? !RUNNING.includes(j.status) : false;
  const isRunning = j ? RUNNING.includes(j.status) : false;

  return (
    <>
      <Dialog
        open
        onClose={onClose}
        width="max-w-3xl"
        title={
          <span className="flex items-center gap-2">
            任务详情
            <span className="font-mono text-xs font-normal text-ink-3">{jobId.slice(0, 8)}</span>
          </span>
        }
        footer={
          j ? (
            <>
              {kind === "infer" && (
                <Button
                  variant="ghost"
                  icon={<AudioWaveform size={15} aria-hidden />}
                  onClick={() => {
                    onClose();
                    onNavigate("studio");
                  }}
                >
                  在工作台打开
                </Button>
              )}
              <span className="flex-1" />
              {isRunning && (
                <Button
                  variant="danger"
                  icon={<Ban size={15} aria-hidden />}
                  loading={busy === "cancel"}
                  disabled={j.cancel_requested === 1}
                  onClick={doCancel}
                >
                  {j.cancel_requested === 1 ? "等待停止" : "取消任务"}
                </Button>
              )}
              {(j.status === "failed" || j.status === "cancelled") && (
                <Button variant="primary" icon={<RotateCcw size={15} aria-hidden />} loading={busy === "retry"} onClick={doRetry}>
                  重试
                </Button>
              )}
              {j.status === "completed" && (
                <Button icon={<Check size={15} aria-hidden />} loading={busy === "accept"} onClick={doAccept}>
                  {j.accepted === 1 ? "取消接受" : "标记接受"}
                </Button>
              )}
              {terminal && (
                <Button variant="danger" icon={<Trash2 size={15} aria-hidden />} onClick={() => setConfirmDelete(true)}>
                  删除
                </Button>
              )}
            </>
          ) : undefined
        }
      >
        {error && !j && (
          <InlineError onRetry={() => setTick((t) => t + 1)}>加载任务详情失败：{error}</InlineError>
        )}
        {!j && !error && (
          <div className="space-y-3">
            <Skeleton className="h-6 w-2/3" />
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        )}
        {j && (
          <div className="space-y-5">
            {/* 概览 */}
            <div className="flex flex-wrap items-center gap-2">
              <StatusBadge tone={statusTone(j.status)}>{STATUS_LABEL[j.status]}</StatusBadge>
              <span className="text-[13px] font-medium">{kindLabel(j)}</span>
              <ProviderBadge providerId={j.provider_id} />
              <span className="text-xs text-ink-3">创建 {fmtTime(j.created_at)}</span>
              {j.elapsed_s != null && <span className="text-xs text-ink-3">耗时 {fmtDur(j.elapsed_s)}</span>}
            </div>

            {j.cancel_requested === 1 && isRunning && (
              <InlineNote tone="warn">已请求取消，任务将在当前阶段边界停止。</InlineNote>
            )}

            {/* 阶段时间线 */}
            <section>
              <h4 className="mb-2 text-[13px] font-semibold">阶段时间线</h4>
              <StageTimeline job={j} />
            </section>

            {/* 安装/校验进度 */}
            {kind !== "infer" && (
              <section>
                <h4 className="mb-2 text-[13px] font-semibold">{kind === "install" ? "安装进度" : "校验进度"}</h4>
                <InstallProgress job={j} />
              </section>
            )}

            {/* 错误 */}
            {j.error && <InlineError>{j.error}</InlineError>}

            {/* 参数 */}
            <section>
              <h4 className="mb-2 text-[13px] font-semibold">参数</h4>
              <ParamGrid job={j} providerName={j.provider_id ? providerMap?.get(j.provider_id)?.name ?? null : null} />
            </section>

            {/* 输入音频 */}
            {inputAudio && (
              <section>
                <h4 className="mb-2 text-[13px] font-semibold">输入音频（只读）</h4>
                <div className="rounded-input border border-line p-3">
                  <div className="mb-2 flex items-center justify-between gap-2 text-[13px]">
                    <span className="truncate font-medium">{inputAudio.original_name}</span>
                    <span className="shrink-0 text-xs text-ink-3">{fmtDur(inputAudio.duration)}</span>
                  </div>
                  <audio controls preload="none" src={api.audioStreamUrl(inputAudio.id)} className="h-9 w-full" aria-label="试听输入音频" />
                </div>
              </section>
            )}

            {/* 结果文件 */}
            {kind === "infer" && (
              <section>
                <h4 className="mb-2 text-[13px] font-semibold">结果文件</h4>
                <OutputFiles files={files} />
              </section>
            )}

            {/* 日志 */}
            <section>
              <h4 className="mb-2 flex items-center gap-1.5 text-[13px] font-semibold">
                <ScrollText size={14} aria-hidden /> 日志
              </h4>
              <JobLog jobId={jobId} active={isRunning} />
            </section>
          </div>
        )}
      </Dialog>

      <ConfirmDialog
        open={confirmDelete}
        onClose={() => setConfirmDelete(false)}
        onConfirm={doDelete}
        title="删除任务"
        confirmLabel="删除任务"
        danger
        loading={busy === "delete"}
      >
        删除该任务会<b>同时删除其输出文件</b>，且不可撤销。原始上传音频不受影响。确定删除吗？
      </ConfirmDialog>
    </>
  );
}