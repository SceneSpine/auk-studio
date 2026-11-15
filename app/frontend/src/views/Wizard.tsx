/**
 * 安装向导 — 六步：检测 → 模型选择 → 第三方许可 → 下载 → 转换 → 验证。
 * 步骤可前后导航，进度存 localStorage（auk-wizard-step），中断可恢复，不强制一次完成。
 * 下载/转换共享同一安装任务（install_json 阶段进度）；验证含真实冒烟测试与结果播放器。
 */
import { useEffect, useState } from "react";
import {
  ArrowLeft, ArrowRight, CheckCircle2, Cloud, FlaskConical, Layers, Play, RefreshCw,
  ShieldCheck, Wand2, Zap,
} from "lucide-react";
import { api } from "../api";
import type { StudioMode, ViewKey } from "../components/AppShell";
import LogViewer from "../components/LogViewer";
import {
  Button, Card, Collapse, InlineError, InlineNote, PageHeader, Progress, Skeleton, StatusBadge, Stepper, cn, useToast,
} from "../components/ui";
import { ReadinessBanner, fmtGb } from "../components/system/common";
import { CheckList } from "../components/system/CheckList";
import { LicenseConsent } from "../components/models/LicenseConsent";
import { InstallProgress } from "../components/models/InstallProgress";
import { MemoryFitBadge, ModelStateBadge, PHASE_LABEL } from "../components/models/common";
import {
  EMPTY_PROVIDER_DRAFT, PROVIDER_KIND_LABEL, PROVIDER_SERVICE_NAME, ProviderFormFields, validateProviderDraft,
  type ProviderDraft, type ProviderErrors,
} from "../components/models/ProviderForm";
import { isOnlineProvider } from "../components/studio/shared";
import { usePoll } from "../hooks";
import type { FileRef, InstallPlan, JobStatus } from "../types";
import { RUNNING, STATUS_LABEL } from "../types";

const STEPS = ["检测", "模型选择", "第三方许可", "下载", "转换", "验证"];

type Aux = {
  variant: "flash" | "base";
  consentIds: string[];
  installJobId: string | null;
  verifyJobId: string | null;
  smokeJobId: string | null;
};
const DEFAULT_AUX: Aux = { variant: "flash", consentIds: [], installJobId: null, verifyJobId: null, smokeJobId: null };

function readStep(): number {
  try {
    const n = parseInt(localStorage.getItem("auk-wizard-step") ?? "0", 10);
    return Number.isFinite(n) ? Math.min(5, Math.max(0, n)) : 0;
  } catch {
    return 0;
  }
}
function readAux(): Aux {
  try {
    const raw = localStorage.getItem("auk-wizard-state");
    return raw ? { ...DEFAULT_AUX, ...(JSON.parse(raw) as Partial<Aux>) } : DEFAULT_AUX;
  } catch {
    return DEFAULT_AUX;
  }
}

const JOB_TONE: Record<JobStatus, "neutral" | "progress" | "ready" | "error" | "unknown"> = {
  queued: "neutral", preparing: "progress", loading_model: "progress", processing: "progress",
  postprocessing: "progress", completed: "ready", failed: "error", cancelled: "unknown",
};

export default function Wizard({ onNavigate }: { onNavigate: (v: ViewKey, m?: StudioMode) => void }) {
  const toast = useToast();
  const [step, setStep] = useState(readStep);
  const [aux, setAux] = useState<Aux>(readAux);
  const [diagTick, setDiagTick] = useState(0);
  const [plan, setPlan] = useState<InstallPlan | null>(null);
  const [planLoading, setPlanLoading] = useState(false);
  const [planError, setPlanError] = useState<string | null>(null);
  const [planTick, setPlanTick] = useState(0);
  const [installBusy, setInstallBusy] = useState(false);
  const [installError, setInstallError] = useState<string | null>(null);
  const [smokeResult, setSmokeResult] = useState<FileRef[] | null>(null);

  /* 远程服务可选路径（远程 AuK / HF Space）：配置后可跳过本地安装，烟测改用远程服务 */
  const [providersTick, setProvidersTick] = useState(0);
  const [onlineDraft, setOnlineDraft] = useState<ProviderDraft>(EMPTY_PROVIDER_DRAFT);
  const [onlineErrors, setOnlineErrors] = useState<ProviderErrors>({});
  const [onlineSaving, setOnlineSaving] = useState(false);
  const [onlineSaveError, setOnlineSaveError] = useState("");

  const modelId = aux.variant === "flash" ? "auk-flash" : "auk-base";

  // 持久化进度
  useEffect(() => {
    try {
      localStorage.setItem("auk-wizard-step", String(step));
      localStorage.setItem("auk-wizard-state", JSON.stringify(aux));
    } catch {
      /* ignore */
    }
  }, [step, aux]);

  const models = usePoll(api.models, 10000, true);
  const providers = usePoll(api.providers, 30000, true, [providersTick]);
  const diag = usePoll(api.diagnostics, 30000, step === 0, [diagTick]);
  const installJob = usePoll(() => api.job(aux.installJobId!), 2000, !!aux.installJobId, [aux.installJobId]);
  const verifyJob = usePoll(() => api.job(aux.verifyJobId!), 2000, !!aux.verifyJobId, [aux.verifyJobId]);
  const smokeJob = usePoll(() => api.job(aux.smokeJobId!), 2000, !!aux.smokeJobId, [aux.smokeJobId]);

  const selectedModel = models.data?.models.find((m) => m.id === modelId) ?? null;
  const deps = models.data?.models.filter((m) => m.role === "dependency") ?? [];
  const onlineProviders = (providers.data?.providers ?? []).filter((p) => p.enabled);
  const onlineConfigured = onlineProviders.length > 0;
  const smokeOnlineProvider = onlineProviders[0] ?? null;
  const alreadyReady = plan?.already_ready || selectedModel?.state === "ready";
  const consentChecked = !!plan && plan.licenses.length > 0 && plan.licenses.every((l) => aux.consentIds.includes(l.id));
  const installDone = installJob.data?.status === "completed" || alreadyReady;

  // 许可 / 下载步骤拉取安装计划
  useEffect(() => {
    if (step !== 2 && step !== 3) return;
    setPlanLoading(true);
    setPlanError(null);
    api
      .installPlan(modelId)
      .then(setPlan)
      .catch((e) => setPlanError((e as Error).message))
      .finally(() => setPlanLoading(false));
  }, [step, modelId, planTick]);

  // 冒烟测试完成后取结果
  useEffect(() => {
    if (smokeJob.data?.status === "completed" && aux.smokeJobId) {
      api
        .jobResult(aux.smokeJobId)
        .then((r) => setSmokeResult(r.files))
        .catch(() => setSmokeResult(null));
    }
  }, [smokeJob.data?.status, aux.smokeJobId]);

  const setConsent = (v: boolean) =>
    setAux((p) => ({ ...p, consentIds: v && plan ? plan.licenses.map((l) => l.id) : [] }));

  const startInstall = async () => {
    if (!plan) return;
    setInstallBusy(true);
    setInstallError(null);
    try {
      const job = await api.installModel(modelId, plan.licenses.map((l) => l.id));
      setAux((p) => ({ ...p, installJobId: job.id }));
      toast("success", "安装任务已创建");
    } catch (e) {
      setInstallError((e as Error).message);
    } finally {
      setInstallBusy(false);
    }
  };

  const cancelInstall = async () => {
    if (!aux.installJobId) return;
    try {
      await api.cancelJob(aux.installJobId);
      toast("info", "已请求取消，下载支持断点续传");
    } catch (e) {
      toast("error", `取消失败：${(e as Error).message}`);
    }
  };

  const retryInstall = async () => {
    if (!aux.installJobId) return;
    try {
      const nj = await api.retryJob(aux.installJobId);
      setAux((p) => ({ ...p, installJobId: nj.id }));
      toast("info", "已重新提交，将从断点续传");
    } catch (e) {
      toast("error", `重试失败：${(e as Error).message}`);
    }
  };

  const startVerify = async () => {
    try {
      const job = await api.verifyModel(modelId);
      setAux((p) => ({ ...p, verifyJobId: job.id }));
      toast("info", "校验任务已创建");
    } catch (e) {
      toast("error", `校验失败：${(e as Error).message}`);
    }
  };

  const retryVerify = async () => {
    if (!aux.verifyJobId) return;
    try {
      const nj = await api.retryJob(aux.verifyJobId);
      setAux((p) => ({ ...p, verifyJobId: nj.id }));
    } catch (e) {
      toast("error", `重试失败：${(e as Error).message}`);
    }
  };

  const saveOnlineProvider = async () => {
    const errs = validateProviderDraft(onlineDraft);
    setOnlineErrors(errs);
    if (Object.keys(errs).length > 0) return;
    setOnlineSaving(true);
    setOnlineSaveError("");
    try {
      await api.createProvider({
        name: onlineDraft.name.trim(),
        kind: onlineDraft.kind,
        base_url: onlineDraft.baseUrl.trim(),
        ...(onlineDraft.apiKey.trim() ? { api_key: onlineDraft.apiKey.trim() } : {}),
      });
      toast("success", `${PROVIDER_KIND_LABEL[onlineDraft.kind]} 服务已保存，可跳过本地模型安装`);
      setOnlineDraft(EMPTY_PROVIDER_DRAFT);
      setOnlineErrors({});
      setProvidersTick((t) => t + 1);
    } catch (e) {
      setOnlineSaveError((e as Error).message);
    } finally {
      setOnlineSaving(false);
    }
  };

  const startSmoke = async () => {
    setSmokeResult(null);
    try {
      // 已配置远程服务（远程 AuK / HF Space）：烟测走 instruct_tts（无需参考音频，不依赖本地模型）
      const job = smokeOnlineProvider
        ? await api.createJob({
            kind: "infer",
            provider_id: smokeOnlineProvider.id,
            mode: "instruct_tts",
            description: "一位平静自然的女性声音",
            target_text: "安装完成，开始创作吧。",
          })
        : await api.createJob({
            mode: "instruct_tts",
            description: "一位平静自然的女性声音",
            target_text: "安装完成，开始创作吧。",
            model_variant: aux.variant,
            bits: 8,
          });
      setAux((p) => ({ ...p, smokeJobId: job.id }));
      toast("info", "冒烟测试任务已创建");
    } catch (e) {
      toast("error", `冒烟测试失败：${(e as Error).message}`);
    }
  };

  const retrySmoke = async () => {
    if (!aux.smokeJobId) return;
    try {
      const nj = await api.retryJob(aux.smokeJobId);
      setAux((p) => ({ ...p, smokeJobId: nj.id }));
      setSmokeResult(null);
    } catch (e) {
      toast("error", `重试失败：${(e as Error).message}`);
    }
  };

  // 已配置远程服务时，许可/下载/转换等本地步骤可跳过（本地流程本身不变）
  const nextDisabled = step === 5 || (step === 2 && !alreadyReady && !consentChecked && !onlineConfigured);
  const done = new Set<number>();
  for (let i = 0; i < step; i++) done.add(i);
  if (installDone) {
    done.add(3);
    done.add(4);
  }
  if (verifyJob.data?.status === "completed") done.add(5);

  const smokeFile = smokeResult?.find((f) => f.kind === "candidate") ?? smokeResult?.[0] ?? null;
  const phase = installJob.data?.install_json?.phase;

  return (
    <div className="space-y-6">
      <PageHeader
        title="安装向导"
        description="六步完成模型就绪。进度自动保存，可随时中断并从上次步骤继续。"
        actions={
          <Button variant="ghost" onClick={() => onNavigate("models")}>前往模型管理</Button>
        }
      />

      <div className="rounded-panel border border-line bg-surface px-5 py-4">
        <Stepper steps={STEPS} current={step} done={[...done]} />
      </div>

      <div className="auk-fade-in" key={step}>
        {/* Step 1 · 检测 */}
        {step === 0 && (
          <div className="space-y-4">
            {diag.error && !diag.data && <InlineError onRetry={() => setDiagTick((t) => t + 1)}>环境检测失败：{diag.error}</InlineError>}
            {!diag.data && !diag.error && <Skeleton className="h-24 w-full rounded-panel" />}
            {diag.data && (
              <>
                <ReadinessBanner
                  level={diag.data.readiness?.level ?? diag.data.overall}
                  reasons={diag.data.readiness?.reasons ?? []}
                  action={
                    <Button size="sm" icon={<RefreshCw size={14} />} onClick={() => setDiagTick((t) => t + 1)}>
                      重新检测
                    </Button>
                  }
                />
                {(diag.data.readiness?.level ?? diag.data.overall) === "blocked" && (
                  <InlineNote tone="warn">存在阻断项，建议先按检查项中的建议修复；你仍可继续查看后续步骤。</InlineNote>
                )}
                <CheckList checks={diag.data.checks} onRetry={() => setDiagTick((t) => t + 1)} />
              </>
            )}
          </div>
        )}

        {/* Step 2 · 模型选择 */}
        {step === 1 && (
          <div className="space-y-4">
            <div role="radiogroup" aria-label="选择主模型" className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {(["flash", "base"] as const).map((v) => {
                const m = models.data?.models.find((x) => x.id === (v === "flash" ? "auk-flash" : "auk-base"));
                const selected = aux.variant === v;
                const Icon = v === "flash" ? Zap : Layers;
                return (
                  <button
                    key={v}
                    role="radio"
                    aria-checked={selected}
                    onClick={() => setAux((p) => ({ ...p, variant: v, consentIds: [], installJobId: null, verifyJobId: null, smokeJobId: null }))}
                    className={cn(
                      "cursor-pointer rounded-panel border p-5 text-left transition-colors",
                      selected ? "border-brand bg-brand-tint" : "border-line bg-surface hover:border-brand/40",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex items-center gap-2.5">
                        <span className={cn("flex h-10 w-10 items-center justify-center rounded-input", selected ? "bg-brand text-white" : "bg-subtle text-ink-2")}>
                          <Icon size={19} aria-hidden />
                        </span>
                        <span>
                          <span className="block text-[15px] font-semibold text-ink">{v === "flash" ? "AuK Flash" : "AuK Base"}</span>
                          <span className="block text-[12px] text-ink-2">{v === "flash" ? "推荐 · 快速生成" : "高质量 · 速度较慢"}</span>
                        </span>
                      </span>
                      <span className={cn("flex h-5 w-5 items-center justify-center rounded-full border", selected ? "border-brand bg-brand text-white" : "border-line")}>
                        {selected && <CheckCircle2 size={14} aria-hidden />}
                      </span>
                    </div>
                    <p className="mt-3 text-[12.5px] leading-5 text-ink-2">
                      {v === "flash"
                        ? "适合日常创作与快速迭代，本机实测 RTF 约 0.5–1.0。"
                        : "追求更高音质时使用，推理更慢、资源占用更高。"}
                    </p>
                    <div className="mt-3 flex flex-wrap items-center gap-2">
                      {m ? <ModelStateBadge state={m.state} /> : <Skeleton className="h-5 w-16" />}
                      {m && <MemoryFitBadge fit={m.memory_fit} />}
                      {m && <span className="text-[11.5px] text-ink-3">下载约 {fmtGb(m.size.download_gb)}</span>}
                    </div>
                  </button>
                );
              })}
            </div>
            <Card title="共用依赖">
              <p className="mb-3 text-[13px] leading-5 text-ink-2">
                Qwen Thinker 语义编码器与 VAE 为 Flash / Base 共用，只需安装一次；已存在则自动复用。
              </p>
              <div className="flex flex-wrap gap-2">
                {deps.length === 0 && <Skeleton className="h-8 w-48" />}
                {deps.map((d) => (
                  <span key={d.id} className="inline-flex items-center gap-2 rounded-input border border-line px-3 py-1.5 text-[12.5px]">
                    {d.display_name}
                    {d.state === "ready" ? (
                      <span className="font-medium text-ok">已存在，将复用</span>
                    ) : (
                      <span className="text-ink-3">将随主模型一并安装</span>
                    )}
                  </span>
                ))}
              </div>
            </Card>

            {/* 远程服务可选路径（远程 AuK / HF Space）：无需本地模型 */}
            <Collapse
              title={
                <span className="inline-flex items-center gap-1.5">
                  <Cloud size={14} aria-hidden />
                  远程服务（可选，无需本地模型）
                </span>
              }
              badge={onlineConfigured ? <StatusBadge tone="ready">已配置 {onlineProviders.length}</StatusBadge> : undefined}
            >
              <div className="space-y-3">
                <p className="text-[13px] leading-5 text-ink-2">
                  配置远程 AuK 服务或 HF Space 后可跳过本地模型安装，使用全部创作能力。生成时音频与文本将发送至远程服务，请确认服务可信。
                </p>
                {onlineConfigured && (
                  <InlineNote>
                    已配置：{onlineProviders.map((p) => `${p.name}（${PROVIDER_KIND_LABEL[p.kind]}）`).join("、")}。可继续本地安装，也可直接前往「验证」步骤用远程服务冒烟测试。
                  </InlineNote>
                )}
                <ProviderFormFields draft={onlineDraft} onChange={setOnlineDraft} errors={onlineErrors} />
                {onlineSaveError && <InlineError>{onlineSaveError}</InlineError>}
                <Button variant="primary" size="sm" loading={onlineSaving} onClick={saveOnlineProvider}>
                  保存{PROVIDER_SERVICE_NAME[onlineDraft.kind]}
                </Button>
              </div>
            </Collapse>
          </div>
        )}

        {/* Step 3 · 第三方许可 */}
        {step === 2 && (
          <div className="space-y-4">
            {onlineConfigured && (
              <InlineNote>可跳过（已配置远程服务）：无需本地模型即可使用全部能力；如需本地推理，仍请完成许可确认。</InlineNote>
            )}
            {planLoading && <Skeleton className="h-48 w-full rounded-panel" />}
            {planError && !planLoading && <InlineError onRetry={() => setPlanTick((t) => t + 1)}>无法获取许可信息：{planError}</InlineError>}
            {plan && !planLoading && (
              <Card title="第三方许可确认">
                {alreadyReady && <div className="mb-3"><InlineNote>该模型已就绪，本地权重将被复用，无需重新安装。</InlineNote></div>}
                <LicenseConsent licenses={plan.licenses} checked={consentChecked} onChange={setConsent} />
                {!consentChecked && !alreadyReady && (
                  <p className="mt-3 text-[12.5px] text-ink-3">勾选上方确认后方可进入下载步骤。</p>
                )}
              </Card>
            )}
          </div>
        )}

        {/* Step 4 · 下载 */}
        {step === 3 && (
          <div className="space-y-4">
            {onlineConfigured && !alreadyReady && (
              <InlineNote>可跳过（已配置远程服务）：下载仅在使用本地 MLX 时需要，可直接前往「验证」步骤。</InlineNote>
            )}
            {alreadyReady ? (
              <InlineNote>已复用本地权重，无需下载。可前往「转换」与「验证」步骤。</InlineNote>
            ) : !aux.installJobId ? (
              <Card title="开始下载与安装">
                <InlineNote>下载支持断点续传：中断或失败后重试会续传已完成部分，而非重新下载。原始权重只读保护。</InlineNote>
                {planError && <div className="mt-3"><InlineError onRetry={() => setPlanTick((t) => t + 1)}>安装计划加载失败：{planError}</InlineError></div>}
                {installError && <div className="mt-3"><InlineError onRetry={startInstall}>安装提交失败：{installError}</InlineError></div>}
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  <Button variant="primary" icon={<ArrowRight size={15} />} disabled={!consentChecked || !plan} loading={installBusy} onClick={startInstall}>
                    开始安装
                  </Button>
                  {!consentChecked && (
                    <>
                      <span className="text-[12.5px] text-ink-3">请先完成第三方许可确认。</span>
                      <Button size="sm" variant="ghost" onClick={() => setStep(2)}>去确认</Button>
                    </>
                  )}
                </div>
              </Card>
            ) : !installJob.data ? (
              <Skeleton className="h-32 w-full rounded-panel" />
            ) : (
              <Card title="下载进度">
                <InstallProgress
                  job={installJob.data}
                  busy={installBusy}
                  onCancel={cancelInstall}
                  onRetry={retryInstall}
                />
                {(phase === "convert" || phase === "quantize" || phase === "smoke" || phase === "done" || installJob.data.status === "completed") && (
                  <div className="mt-3"><InlineNote>下载与校验已完成，可前往「转换」步骤查看后续进度。</InlineNote></div>
                )}
                <div className="mt-4">
                  <p className="mb-2 text-[12px] font-medium text-ink-2">任务日志</p>
                  <LogViewer jobId={installJob.data.id} active={RUNNING.includes(installJob.data.status)} />
                </div>
              </Card>
            )}
          </div>
        )}

        {/* Step 5 · 转换 */}
        {step === 4 && (
          <div className="space-y-4">
            {onlineConfigured && !alreadyReady && (
              <InlineNote>可跳过（已配置远程服务）：转换仅在使用本地 MLX 时需要，可直接前往「验证」步骤。</InlineNote>
            )}
            {alreadyReady ? (
              <InlineNote>模型已就绪，转换产物已存在，无需再次转换。</InlineNote>
            ) : !aux.installJobId ? (
              <Card title="MLX 转换与量化">
                <p className="text-[13px] leading-5 text-ink-2">转换将在下载与校验完成后自动开始。请先完成下载步骤。</p>
                <Button className="mt-3" size="sm" onClick={() => setStep(3)}>前往下载</Button>
              </Card>
            ) : !installJob.data ? (
              <Skeleton className="h-32 w-full rounded-panel" />
            ) : (
              <Card title="转换进度">
                {(phase === "download" || phase === "verify" || phase === "prepare") && (
                  <div className="mb-3"><InlineNote>当前仍在「{phase ? PHASE_LABEL[phase] : "准备"}」阶段，转换将在下载与校验完成后自动开始。</InlineNote></div>
                )}
                <InstallProgress job={installJob.data} onCancel={cancelInstall} onRetry={retryInstall} />
                {installJob.data.status === "completed" && (
                  <div className="mt-3"><InlineNote>转换与量化已完成，可前往「验证」步骤进行校验与冒烟测试。</InlineNote></div>
                )}
                <div className="mt-4">
                  <p className="mb-2 text-[12px] font-medium text-ink-2">任务日志</p>
                  <LogViewer jobId={installJob.data.id} active={RUNNING.includes(installJob.data.status)} />
                </div>
              </Card>
            )}
          </div>
        )}

        {/* Step 6 · 验证 */}
        {step === 5 && (
          <div className="space-y-4">
            <Card title="权重校验">
              <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" icon={<ShieldCheck size={14} />} onClick={startVerify} disabled={!!verifyJob.data && RUNNING.includes(verifyJob.data.status)}>
                  开始校验
                </Button>
                <span className="text-[12.5px] text-ink-3">逐文件 SHA256 对照 manifest，确保权重完整。</span>
              </div>
              {verifyJob.data && (
                <div className="mt-4 space-y-3">
                  <InstallProgress job={verifyJob.data} onRetry={retryVerify} />
                  <LogViewer jobId={verifyJob.data.id} active={RUNNING.includes(verifyJob.data.status)} />
                </div>
              )}
            </Card>

            <Card title="冒烟测试">
              <p className="mb-3 text-[13px] leading-5 text-ink-2">
                {smokeOnlineProvider
                  ? `已配置${PROVIDER_SERVICE_NAME[smokeOnlineProvider.kind]}：将使用「${smokeOnlineProvider.name}」执行一条音色设计任务（「一位平静自然的女性声音」朗读「安装完成，开始创作吧。」，无需参考音频），验证远程推理链路。${
                      smokeOnlineProvider.kind === "hf_space"
                        ? "文本会发送至该 HF Space（共享演示服务，可能排队或冷启动）。"
                        : "文本会发送至远程服务。"
                    }`
                  : "创建一个真实的描述式 TTS 任务（「一位平静自然的女性声音」朗读「安装完成，开始创作吧。」），验证整条推理链路可用。"}
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  variant="primary"
                  icon={<FlaskConical size={14} />}
                  onClick={startSmoke}
                  disabled={(!smokeOnlineProvider && selectedModel?.state !== "ready") || (!!smokeJob.data && RUNNING.includes(smokeJob.data.status))}
                >
                  冒烟测试
                </Button>
                {!smokeOnlineProvider && selectedModel?.state !== "ready" && (
                  <span className="text-[12.5px] text-ink-3">模型就绪后可进行冒烟测试。</span>
                )}
              </div>

              {smokeJob.data && (
                <div className="mt-4 space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge tone={JOB_TONE[smokeJob.data.status]}>{STATUS_LABEL[smokeJob.data.status]}</StatusBadge>
                    {smokeJob.data.stage_detail && <span className="text-[12.5px] text-ink-2">{smokeJob.data.stage_detail}</span>}
                  </div>
                  {RUNNING.includes(smokeJob.data.status) && <Progress label="冒烟测试进度" />}
                  {smokeJob.data.status === "failed" && (
                    <InlineError onRetry={retrySmoke}>{smokeJob.data.error || "冒烟测试失败"}</InlineError>
                  )}
                  {smokeJob.data.status === "completed" && smokeFile && (
                    <div className="space-y-3 rounded-input border border-line bg-subtle/40 p-4">
                      <p className="flex items-center gap-1.5 text-[13px] font-medium text-ok">
                        <CheckCircle2 size={15} aria-hidden /> 推理链路验证通过，试听生成结果：
                      </p>
                      <audio controls src={smokeFile.url ?? api.outputUrl(smokeFile.id)} className="w-full" />
                      <Button
                        variant="primary"
                        icon={<Play size={15} />}
                        onClick={() => onNavigate("studio", isOnlineProvider(smokeJob.data?.provider_id) ? "tts" : "edit")}
                      >
                        开始创作
                      </Button>
                    </div>
                  )}
                  <LogViewer jobId={smokeJob.data.id} active={RUNNING.includes(smokeJob.data.status)} />
                </div>
              )}
            </Card>
          </div>
        )}
      </div>

      {/* 步骤导航 */}
      <div className="flex items-center justify-between gap-3 border-t border-line pt-4">
        <Button icon={<ArrowLeft size={15} />} disabled={step === 0} onClick={() => setStep((s) => Math.max(0, s - 1))}>
          上一步
        </Button>
        <span className="text-[12.5px] text-ink-3">
          第 {step + 1} / {STEPS.length} 步 · {STEPS[step]} · 进度已自动保存
        </span>
        {step < 5 ? (
          <Button variant="primary" icon={<ArrowRight size={15} />} disabled={nextDisabled} onClick={() => setStep((s) => Math.min(5, s + 1))}>
            下一步
          </Button>
        ) : (
          <Button
            variant="primary"
            icon={<Wand2 size={15} />}
            onClick={() => onNavigate("studio", onlineConfigured && !alreadyReady ? "tts" : "edit")}
          >
            开始创作
          </Button>
        )}
      </div>
    </div>
  );
}