/** 生成配置（右栏 35%）：模型选择 + 资源适配 + 高级参数 + 提交/取消 + 任务进度与日志。 */
import { useState } from "react";
import { ChevronDown, Gauge, RotateCcw, SlidersHorizontal, Sparkles, Square } from "lucide-react";
import { api } from "../../api";
import type { Job, JobStatus, ModelsResponse, Preflight, Settings } from "../../types";
import { RUNNING, STATUS_LABEL, fmtDur } from "../../types";
import LogViewer from "../LogViewer";
import type { StudioMode, ViewKey } from "../AppShell";
import {
  Button, Collapse, Field, InlineError, InlineNote, Input, Kbd, Progress,
  Select, StatusBadge, Switch, cn, type StatusTone,
} from "../ui";
import { variantOfModelId, type GenConfig } from "./shared";

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

const LEVEL_LABEL: Record<Preflight["level"], { label: string; tone: StatusTone }> = {
  ready: { label: "资源充足", tone: "ready" },
  caution: { label: "需注意", tone: "warn" },
  blocked: { label: "阻断", tone: "error" },
  unknown: { label: "未知", tone: "unknown" },
};

interface Props {
  config: GenConfig;
  onConfigChange: (v: GenConfig | ((p: GenConfig) => GenConfig)) => void;
  models: ModelsResponse | null;
  modelsError: string | null;
  /** /api/models 可用时才调用 activate（旧后端降级时切换在提交时生效） */
  canActivate: boolean;
  settings: Settings | null;
  mode: StudioMode;
  audioDuration: number | null;
  job: Job | null;
  submitting: boolean;
  canSubmit: boolean;
  submitHint: string | null;
  error: string;
  preflight: Preflight | null;
  preflightBusy: boolean;
  onPreflight: () => void;
  onSubmit: () => void;
  onCancel: () => void;
  onRetry: () => void;
  onNavigate: (v: ViewKey, m?: StudioMode) => void;
}

export default function ConfigPanel({
  config, onConfigChange, models, modelsError, canActivate, settings, mode, audioDuration,
  job, submitting, canSubmit, submitHint, error, preflight, preflightBusy,
  onPreflight, onSubmit, onCancel, onRetry, onNavigate,
}: Props) {
  const [openSmall, setOpenSmall] = useState(true);
  const [activateMsg, setActivateMsg] = useState("");

  const isRunning = !!job && RUNNING.includes(job.status);
  const mainModels = models?.models.filter((m) => m.role === "main") ?? [];
  const selectedModel = mainModels.find((m) => variantOfModelId(m.id) === config.modelVariant) ?? null;
  const workerLoaded = !!models?.worker.model_loaded && models?.worker.model_variant === config.modelVariant;

  const set = <K extends keyof GenConfig>(key: K, value: GenConfig[K]) => onConfigChange((c) => ({ ...c, [key]: value }));

  const changeVariant = (v: "flash" | "base") => {
    set("modelVariant", v);
    setActivateMsg("");
    const target = mainModels.find((m) => variantOfModelId(m.id) === v);
    if (target && target.state === "ready" && canActivate) {
      // 切换常驻模型：worker 在当前任务结束后加载，运行中不强制卸载
      api.activateModel(target.id)
        .then((r) => setActivateMsg(r.message))
        .catch((e) => setActivateMsg((e as Error).message));
    }
  };

  const fitBadge = selectedModel?.memory_fit;

  return (
    <section className="flex flex-col rounded-panel border border-line bg-surface lg:h-full lg:min-h-0">
      <header className="flex shrink-0 items-center justify-between gap-3 border-b border-line px-5 py-3.5">
        <h3 className="text-[15px] font-semibold leading-6">生成配置</h3>
        <button
          className="inline-flex cursor-pointer items-center gap-1 text-xs text-ink-2 lg:hidden"
          onClick={() => setOpenSmall((o) => !o)}
          aria-expanded={openSmall}
        >
          {openSmall ? "收起" : "展开"}
          <ChevronDown size={14} className={cn("transition-transform", openSmall && "rotate-180")} aria-hidden />
        </button>
      </header>
      <div className={cn("space-y-4 p-5 lg:min-h-0 lg:flex-1 lg:overflow-y-auto", !openSmall && "hidden lg:block")}>
        {/* 模型选择 */}
        <Field
          label="模型"
          hint={config.modelVariant === "flash" ? "AuK-Flash：4 步，快，适合词级替换" : "AuK Base：编辑跟随更准，速度较慢"}
        >
          <Select value={config.modelVariant} onChange={(e) => changeVariant(e.target.value as "flash" | "base")}>
            {mainModels.length > 0 ? (
              mainModels.map((m) => (
                <option key={m.id} value={variantOfModelId(m.id)} disabled={m.state !== "ready"}>
                  {m.display_name}{m.state === "ready" ? "" : "（未安装）"}
                </option>
              ))
            ) : (
              <>
                <option value="flash">AuK-Flash（4 步，快）</option>
                <option value="base">AuK Base（更准）</option>
              </>
            )}
          </Select>
        </Field>

        <div className="flex flex-wrap items-center gap-1.5">
          {selectedModel ? (
            <StatusBadge tone={selectedModel.state === "ready" ? "ready" : "warn"}>
              {selectedModel.state === "ready" ? "已就绪" : "未安装"}
            </StatusBadge>
          ) : (
            <StatusBadge tone="unknown">状态不可用</StatusBadge>
          )}
          {selectedModel?.state === "ready" && (
            <StatusBadge tone={workerLoaded ? "ready" : "neutral"}>
              {workerLoaded ? "已加载" : "提交时加载"}
            </StatusBadge>
          )}
          {fitBadge && fitBadge !== "unknown" && (
            <StatusBadge tone={fitBadge === "comfortable" ? "ready" : fitBadge === "tight" ? "warn" : "error"}>
              {fitBadge === "comfortable" ? "内存适配" : fitBadge === "tight" ? "内存偏紧" : "内存不足"}
            </StatusBadge>
          )}
        </div>
        {activateMsg && <p className="text-xs leading-[18px] text-ink-3">{activateMsg}</p>}
        {selectedModel && selectedModel.state !== "ready" && (
          <InlineNote tone="warn">
            所选模型未安装。
            <button className="ml-1 cursor-pointer font-medium underline" onClick={() => onNavigate("wizard")}>去安装</button>
            ，或切换到已就绪的模型。
          </InlineNote>
        )}
        {modelsError && !models && (
          <InlineNote tone="warn">模型状态不可用（{modelsError}）。请确认后端服务运行中；提交仍会尝试执行。</InlineNote>
        )}

        {/* 推荐配置 */}
        <p className="rounded-input bg-subtle px-3 py-2 text-xs leading-[18px] text-ink-2">
          实测推荐：8-bit（与 fp32 听感一致）
          {settings?.default_sequential === "1" ? " · Sequential 逐栈加载更省内存" : ""}
          {settings && (
            <span className="text-ink-3">
              （当前设置默认：{settings.default_bits === "None" ? "fp32" : `${settings.default_bits}-bit`} · Sequential {settings.default_sequential === "1" ? "开" : "关"}）
            </span>
          )}
        </p>

        {/* 资源适配检查 */}
        <div className="space-y-2">
          <Button size="sm" variant="outline" icon={<Gauge size={14} />} loading={preflightBusy} onClick={onPreflight} className="w-full">
            资源适配检查（提交前可选）
          </Button>
          {preflight && (
            <div className="space-y-1.5 rounded-input border border-line p-3 text-xs leading-[18px]">
              <StatusBadge tone={LEVEL_LABEL[preflight.level].tone}>{LEVEL_LABEL[preflight.level].label}</StatusBadge>
              {preflight.reasons.length > 0 && (
                <ul className="list-disc space-y-0.5 pl-4 text-ink-2">
                  {preflight.reasons.map((r, i) => <li key={i}>{r}</li>)}
                </ul>
              )}
              <p className="text-ink-3">
                {preflight.estimates.note}
                {preflight.estimates.peak_memory_gb != null && ` · 峰值内存约 ${preflight.estimates.peak_memory_gb}GB`}
                {preflight.estimates.rtf_range && ` · RTF ${preflight.estimates.rtf_range[0]}–${preflight.estimates.rtf_range[1]}`}
              </p>
            </div>
          )}
        </div>

        {/* 高级参数 */}
        <Collapse title={<span className="inline-flex items-center gap-1.5"><SlidersHorizontal size={14} aria-hidden />高级参数</span>}>
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="随机种子" hint="默认 1（可复现）；留空 = 随机">
                <Input
                  value={config.seed}
                  onChange={(e) => set("seed", e.target.value.replace(/[^0-9]/g, ""))}
                  placeholder="随机"
                  inputMode="numeric"
                />
              </Field>
              <Field
                label="精度"
                hint={config.bits === "8" ? "官方推荐，与 fp32 听感一致" : "原始精度，内存占用最高"}
              >
                <Select value={config.bits} onChange={(e) => set("bits", e.target.value as GenConfig["bits"])}>
                  <option value="8">8-bit（推荐）</option>
                  <option value="fp32">fp32</option>
                </Select>
              </Field>
              <Field label="目标时长（秒）" hint="留空 = 自动">
                <Input
                  value={config.genSeconds}
                  onChange={(e) => set("genSeconds", e.target.value.replace(/[^0-9.]/g, ""))}
                  placeholder={audioDuration != null ? `自动（源 ${audioDuration.toFixed(1)}s）` : "自动（按文本长度估算）"}
                  inputMode="decimal"
                />
              </Field>
              {config.modelVariant === "base" && (
                <Field label="ODE 步数（NFE）" hint="步数越多编辑跟随越准，越慢">
                  <Select value={config.nfe} onChange={(e) => set("nfe", e.target.value)}>
                    <option value="16">16（较快）</option>
                    <option value="32">32（官方默认）</option>
                    <option value="48">48（更准）</option>
                  </Select>
                </Field>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={config.sequential} onChange={(v) => set("sequential", v)} label="Sequential 逐栈加载" />
              <span className="text-xs text-ink-2">Sequential 逐栈加载（更省内存，每次重读权重）</span>
            </div>
          </div>
        </Collapse>

        {error && <InlineError>{error}</InlineError>}

        {/* 任务进度（不伪造百分比） */}
        {job && (
          <div className="space-y-2.5 rounded-input border border-line p-3.5">
            <div className="flex items-center justify-between gap-2">
              <StatusBadge tone={JOB_TONE[job.status]}>{STATUS_LABEL[job.status]}</StatusBadge>
              <span className="text-xs text-ink-3">
                {job.elapsed_s != null ? `耗时 ${fmtDur(job.elapsed_s)}` : isRunning ? "进行中" : ""}
              </span>
            </div>
            <div className="text-xs text-ink-2">阶段：{job.stage_detail || "—"}</div>
            {isRunning && <Progress value={null} label="生成进度（无真实百分比，不确定模式）" />}
            {isRunning && !!job.cancel_requested && (
              <p className="text-xs leading-[18px] text-warn">正在请求停止：推理无法安全中断，将在当前阶段结束后停止。</p>
            )}
            {job.status === "failed" && <InlineError>{job.error || "任务失败"}</InlineError>}
            {(job.status === "failed" || job.status === "cancelled") && (
              <Button size="sm" icon={<RotateCcw size={14} />} onClick={onRetry}>重试</Button>
            )}
            {job.status === "completed" && (
              <p className="text-xs text-ink-3">
                RTF：{job.rtf ?? "—"}{job.peak_memory_gb ? ` · 峰值内存 ${job.peak_memory_gb}GB` : ""}
                {job.output_duration != null ? ` · 输出 ${fmtDur(job.output_duration)}` : ""}
              </p>
            )}
            <Collapse title="查看日志">
              <LogViewer jobId={job.id} active={isRunning} />
            </Collapse>
          </div>
        )}
      </div>

      {/* 提交区固定底部：主操作永远可见，不随配置滚动 */}
      <div className={cn("shrink-0 space-y-2 border-t border-line p-4", !openSmall && "hidden lg:block")}>
        {isRunning ? (
          <Button variant="danger" className="w-full" icon={<Square size={15} />} onClick={onCancel}>
            {job?.cancel_requested ? "正在请求停止…" : "取消任务"}
          </Button>
        ) : (
          <Button
            variant="primary"
            size="lg"
            className="w-full"
            icon={<Sparkles size={16} />}
            disabled={!canSubmit}
            loading={submitting}
            onClick={onSubmit}
          >
            生成候选音频
          </Button>
        )}
        {submitHint && !isRunning && <p className="text-xs leading-[18px] text-warn">{submitHint}</p>}
        <p className="flex flex-wrap items-center gap-1 text-[11px] text-ink-3">
          <Kbd>⌘</Kbd>+<Kbd>↵</Kbd> 快速提交 · 单任务串行 · 本机 MLX/Metal 推理 · 不上传云端
        </p>
      </div>
    </section>
  );
}