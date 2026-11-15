/**
 * 创作工作台 Studio（02-UI-UX设计规范 §3.3 / PRD §3.2）。
 * 结构：主音频区 → 模式 Tabs（能力门禁）→ 内容编辑 65% + 生成配置 35% → 结果抽屉。
 * 完整移植旧 Workspace 的编辑/生成/结果/拼接链路，并扩展 TTS / 音色设计 / 音色重塑 / 情绪编辑。
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { AudioWaveform, Mic, Palette, Smile, Sparkles } from "lucide-react";
import { api } from "../api";
import type { AudioMeta, Capabilities, FileRef, Job, ModelInfo, ModelsResponse, Preflight, Provider, Settings, Waveform } from "../types";
import { RUNNING } from "../types";
import { usePoll } from "../hooks";
import type { StudioMode, ViewKey } from "../components/AppShell";
import type { Region } from "../components/WavePlayer";
import { Button, InlineNote, Kbd, StatusBadge, Tabs, Tooltip, useDraft, useToast } from "../components/ui";
import AudioStage from "../components/studio/AudioStage";
import ConfigPanel from "../components/studio/ConfigPanel";
import DesignPanel from "../components/studio/DesignPanel";
import EditPanel from "../components/studio/EditPanel";
import EmotionPanel from "../components/studio/EmotionPanel";
import ResultsDrawer from "../components/studio/ResultsDrawer";
import TimbrePanel from "../components/studio/TimbrePanel";
import TtsPanel from "../components/studio/TtsPanel";
import { toggleActive } from "../components/studio/playback";
import {
  CONFIG_DEFAULTS, DESIGN_DEFAULTS, EDIT_DEFAULTS, EMOTION_DEFAULTS, FALLBACK_CAPS,
  MODE_TITLE, TASK_FOR_MODE, TIMBRE_DEFAULTS, TTS_DEFAULTS,
  capFor, editExtraText, payloadFromJob, variantOfModelId,
  type DesignDraft, type EditDraft, type EmotionDraft, type GenConfig, type TimbreDraft, type TtsDraft,
} from "../components/studio/shared";

const MODE_ICONS: Record<StudioMode, typeof AudioWaveform> = {
  edit: AudioWaveform,
  tts: Mic,
  design: Sparkles,
  timbre: Palette,
  emotion: Smile,
};
const MODE_ORDER: StudioMode[] = ["edit", "tts", "design", "timbre", "emotion"];

export default function Studio({
  mode,
  onModeChange,
  onNavigate,
}: {
  mode: StudioMode;
  onModeChange: (m: StudioMode) => void;
  onNavigate: (v: ViewKey, m?: StudioMode) => void;
}) {
  const toast = useToast();

  /* ---------------- 主音频 ---------------- */
  const [audio, setAudio] = useState<AudioMeta | null>(null);
  const [waveform, setWaveform] = useState<Waveform | null>(null);
  const [recent, setRecent] = useState<AudioMeta[]>([]);
  const [mainRegion, setMainRegion] = useState<Region | null>(null);

  /* ---------------- 能力 / 模型 / 设置 ---------------- */
  const [caps, setCaps] = useState<Capabilities | null>(null);
  const [capsFailed, setCapsFailed] = useState(false);
  const { data: models, error: modelsError } = usePoll<ModelsResponse>(() => api.models(), 10000, true);
  const [legacyModels, setLegacyModels] = useState<ModelsResponse | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);

  /* 远程 AuK 服务：null = 接口不可用（降级只显示本地） */
  const [providerList, setProviderList] = useState<Provider[] | null>(null);
  const [providersReady, setProvidersReady] = useState(false);

  /* /api/models 不可用时（旧后端）降级到 /api/model/status，仍展示真实就绪状态 */
  useEffect(() => {
    if (!modelsError || models) return;
    let alive = true;
    const load = () =>
      api.modelStatus()
        .then((m) => {
          if (!alive) return;
          const mk = (id: string, name: string, ready: boolean, desc: string): ModelInfo => ({
            id,
            display_name: name,
            family: "auk",
            role: "main",
            description: desc,
            source: { repo: "", revision: "", urls: [] },
            license: { id: "mit", name: "MIT", url: "", commercial: true, summary: "许可以模型管理页为准" },
            state: ready ? "ready" : "not_installed",
            downloaded: ready,
            converted: ready,
            quantized: ready,
            size: { download_gb: 0, converted_gb: 0, disk_gb: 0 },
            memory_fit: "unknown",
            depends_on: [],
            active: false,
          });
          setLegacyModels({
            models: [
              mk("auk-flash", "AuK-Flash", m.downloaded && m.converted, "4 步快速生成（旧版状态接口）"),
              mk("auk-base", "AuK Base", !!m.base_ready, "多步高质量生成（旧版状态接口）"),
            ],
            active: null,
            worker: m.worker,
          });
        })
        .catch(() => {});
    void load();
    const t = setInterval(load, 30000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, [modelsError, models]);
  const effectiveModels = models ?? legacyModels;

  /* ---------------- 草稿（模式切换 / 刷新不丢） ---------------- */
  const [editDraft, setEditDraft, clearEditDraft] = useDraft<EditDraft>("studio-edit", EDIT_DEFAULTS);
  const [ttsDraft, setTtsDraft] = useDraft<TtsDraft>("studio-tts", TTS_DEFAULTS);
  const [designDraft, setDesignDraft] = useDraft<DesignDraft>("studio-design", DESIGN_DEFAULTS);
  const [timbreDraft, setTimbreDraft] = useDraft<TimbreDraft>("studio-timbre", TIMBRE_DEFAULTS);
  const [emotionDraft, setEmotionDraft] = useDraft<EmotionDraft>("studio-emotion", EMOTION_DEFAULTS);
  const [config, setConfig] = useDraft<GenConfig>("studio-config", CONFIG_DEFAULTS);
  const [crossfadeMs, setCrossfadeMs] = useState("30");

  /* TTS 参考音频（独立于主音频） */
  const [ttsRef, setTtsRef] = useState<AudioMeta | null>(null);

  /* ---------------- 远程 Provider 派生状态（auk_remote 全部模式可用） ---------------- */
  const onlineProvider = providerList?.find((p) => p.id === config.providerId) ?? null;
  const isOnline = !!onlineProvider;

  /* 草稿中的远程 provider 已删除/停用/接口不可用 → 静默切回本地默认 */
  useEffect(() => {
    if (!providersReady || config.providerId === "local") return;
    if (!providerList?.some((p) => p.id === config.providerId)) {
      setConfig((c) => ({ ...c, providerId: "local" }));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [providersReady, providerList, config.providerId]);

  /* ---------------- 任务 ---------------- */
  const [jobId, setJobId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [preflight, setPreflight] = useState<Preflight | null>(null);
  const [preflightBusy, setPreflightBusy] = useState(false);
  const [currentResult, setCurrentResult] = useState<{ job: Job; files: FileRef[] } | null>(null);
  const [historyJobs, setHistoryJobs] = useState<Job[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);

  const [jobPollActive, setJobPollActive] = useState(false);
  const { data: job, setData: setJob } = usePoll<Job>(() => api.job(jobId!), 1200, jobPollActive, [jobId]);
  const isRunning = !!job && RUNNING.includes(job.status);
  useEffect(() => {
    if (job && !RUNNING.includes(job.status)) setJobPollActive(false);
  }, [job?.status]);

  /* ---------------- 初始化 ---------------- */
  const hadConfigDraft = useRef<boolean>(
    (() => {
      try {
        return localStorage.getItem("auk-draft:studio-config") != null;
      } catch {
        return false;
      }
    })(),
  );
  useEffect(() => {
    api.capabilities()
      .then(setCaps)
      .catch(() => {
        setCaps(FALLBACK_CAPS);
        setCapsFailed(true);
      });
    api.audioList().then(setRecent).catch(() => {});
    api.providers()
      .then((r) => setProviderList(r.providers.filter((p) => p.enabled)))
      .catch(() => setProviderList(null))
      .finally(() => setProvidersReady(true));
    // 一次性迁移：旧草稿的空种子（旧默认=随机）升级为默认 1；用户主动设的值不动
    try {
      if (!localStorage.getItem("auk-seed-default-v1")) {
        localStorage.setItem("auk-seed-default-v1", "1");
        setConfig((c) => (c.seed.trim() === "" ? { ...c, seed: "1" } : c));
      }
    } catch {
      /* ignore */
    }
    api.settings()
      .then((s) => {
        setSettings(s);
        setCrossfadeMs(s.crossfade_ms || "30");
        if (!hadConfigDraft.current) {
          setConfig((c) => ({
            ...c,
            bits: s.default_bits === "8" ? "8" : "fp32",
            sequential: s.default_sequential === "1",
            modelVariant: s.default_variant === "base" ? "base" : "flash",
          }));
        }
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* 恢复 TTS 上传参考（刷新后） */
  useEffect(() => {
    if (ttsDraft.refKind === "upload" && ttsDraft.refAudioId) {
      api.audioGet(ttsDraft.refAudioId)
        .then(setTtsRef)
        .catch(() => setTtsDraft((d) => ({ ...d, refAudioId: null })));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  /* ---------------- 音频装载 ---------------- */
  const loadAudio = useCallback(async (a: AudioMeta) => {
    setAudio(a);
    setMainRegion(null);
    setJobId(null);
    setJob(null);
    setJobPollActive(false);
    setCurrentResult(null);
    setError("");
    setWaveform(a.waveform ?? null);
    if (!a.waveform) {
      try {
        setWaveform(await api.waveform(a.id));
      } catch {
        setWaveform(null);
      }
    }
    api.audioList().then(setRecent).catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const replaceAudio = () => {
    setAudio(null);
    setWaveform(null);
    setMainRegion(null);
    setJobId(null);
    setJob(null);
    setJobPollActive(false);
    setCurrentResult(null);
    setError("");
  };

  /* ---------------- 任务结果 / 候选历史 ---------------- */
  useEffect(() => {
    if (!job) return;
    if (job.status === "completed") {
      api.jobResult(job.id)
        .then((r) => {
          setCurrentResult({ job: r.job ?? job, files: r.files });
          setDrawerOpen(true);
        })
        .catch((e) => setError(`结果加载失败：${(e as Error).message}`));
    }
    if (job.status === "failed") setCurrentResult(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.id, job?.status]);

  const refreshHistory = useCallback(() => {
    api.jobs("completed", "infer")
      .then((list) => {
        const relevant = list.filter((j) => {
          // 旧后端无 kind 字段：缺省视为推理任务
          if (j.kind && j.kind !== "infer") return false;
          if (mode === "design") return j.mode === "instruct_tts";
          if (mode === "tts") {
            if (isOnline) return j.mode === "tts" && j.provider_id === config.providerId;
            if (ttsRef && j.audio_id === ttsRef.id) return true;
            if (ttsDraft.voiceId && j.voice_id === ttsDraft.voiceId) return true;
            return false;
          }
          return !!audio && j.audio_id === audio.id;
        });
        setHistoryJobs(relevant.slice(0, 10));
      })
      .catch(() => setHistoryJobs([]));
  }, [mode, audio, ttsRef, ttsDraft.voiceId, isOnline, config.providerId]);

  useEffect(() => {
    // 仅在无任务或任务到达终态时刷新候选历史，避免轮询期间重复请求
    if (!job || job.status === "completed" || job.status === "failed" || job.status === "cancelled") refreshHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshHistory, job?.status]);

  /* 模式切换：无结果且无运行任务时收起结果停靠区，减少噪音 */
  useEffect(() => {
    if (!currentResult && !isRunning) setDrawerOpen(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mode]);

  /* ---------------- 能力门禁 / 提交校验 ---------------- */
  const cap = capFor(caps, mode);
  const mainModels = effectiveModels?.models.filter((m) => m.role === "main") ?? [];
  const readyMains = mainModels.filter((m) => m.state === "ready");
  const noMainModel = !!effectiveModels && readyMains.length === 0;
  const selectedReady = !effectiveModels || mainModels.some((m) => variantOfModelId(m.id) === config.modelVariant && m.state === "ready");
  const audioNeeded = mode === "edit" || mode === "timbre" || mode === "emotion";

  let contentOk = false;
  let contentHint = "";
  if (mode === "edit") {
    contentOk =
      editDraft.sub === "replace"
        ? editDraft.segOriginal.trim() !== "" && editDraft.segReplacement.trim() !== ""
        : editDraft.sub === "full"
          ? editDraft.targetText.trim() !== ""
          : editDraft.customInstruction.trim() !== "";
    contentHint = editDraft.sub === "replace" ? "请填写原片段与替换文本" : editDraft.sub === "full" ? "请填写替换后的完整文本" : "请填写自由指令";
  } else if (mode === "tts") {
    // 本地与远程均为零样本合成：文本 + 参考音色（远程需要参考音频上传）
    const hasRef = (ttsDraft.refKind === "upload" && !!ttsRef) || (ttsDraft.refKind === "voice" && !!ttsDraft.voiceId);
    contentOk = ttsDraft.text.trim() !== "" && hasRef;
    contentHint = ttsDraft.text.trim() === "" ? "请填写朗读文本" : "请选择参考音频或音色库参考（无参考请改用音色设计）";
  } else if (mode === "design") {
    contentOk = designDraft.description.trim() !== "" && designDraft.text.trim() !== "";
    contentHint = "请填写音色描述与试听文案";
  } else if (mode === "timbre") {
    contentOk = timbreDraft.description.trim() !== "";
    contentHint = "请填写目标音色描述";
  } else {
    contentOk = emotionDraft.emotion !== "";
    contentHint = "请选择目标情绪";
  }

  /* 远程分支：全部模式可用，不依赖本地模型；内容/源音频要求与本地一致 */
  const canSubmit = isOnline
    ? contentOk && !!onlineProvider?.enabled && (!audioNeeded || !!audio) && !isRunning && !submitting
    : cap.state !== "not_supported" && !noMainModel && selectedReady &&
      (!audioNeeded || !!audio) && contentOk && !isRunning && !submitting;

  const submitHint = isOnline
    ? audioNeeded && !audio ? "请先上传源音频"
      : !contentOk ? contentHint : null
    : cap.state === "not_supported" ? "当前 MLX 分支不支持该能力，无法提交"
      : noMainModel ? "请先安装主模型（Flash / Base）"
        : !selectedReady ? "所选模型未安装，请切换模型或前往安装"
          : audioNeeded && !audio ? "请先上传源音频"
            : !contentOk ? contentHint
              : null;

  /* ---------------- 提交 / 取消 / 重试 / 重做 ---------------- */
  const buildPayload = (): Record<string, unknown> | null => {
    /* 远程 AuK：与本地相同的完整 payload + provider_id（音频/文本/参数由后端转发远程） */
    const common = {
      kind: "infer",
      ...(isOnline ? { provider_id: config.providerId } : {}),
      model_variant: config.modelVariant,
      bits: config.bits === "fp32" ? null : Number(config.bits),
      sequential: config.sequential,
      seed: config.seed.trim() === "" ? null : Number(config.seed),
      gen_seconds: config.genSeconds.trim() === "" ? null : Number(config.genSeconds),
      nfe: config.modelVariant === "base" ? Number(config.nfe) : null,
    };
    if (mode === "edit") {
      if (!audio) return null;
      const d = editDraft;
      return {
        ...common,
        audio_id: audio.id,
        mode: d.sub,
        original_text: d.originalText,
        target_text: d.targetText,
        segment: { original: d.segOriginal, replacement: d.segReplacement },
        // full 模式不附加中文风格指令（TTS 模板后附加会被朗读——实测 bug）
        instruction: d.sub === "custom" ? d.customInstruction : d.sub === "replace" ? editExtraText(d) : "",
      };
    }
    if (mode === "tts") {
      const ref = ttsDraft.refKind === "upload" ? ttsRef : null;
      const voiceId = ttsDraft.refKind === "voice" ? ttsDraft.voiceId : null;
      if (!ref && !voiceId) return null;
      return { ...common, mode: "tts", audio_id: ref?.id ?? null, voice_id: voiceId, target_text: ttsDraft.text };
    }
    if (mode === "design") {
      return { ...common, mode: "instruct_tts", audio_id: null, description: designDraft.description, target_text: designDraft.text };
    }
    if (mode === "timbre") {
      if (!audio) return null;
      return { ...common, mode: "timbre", audio_id: audio.id, description: timbreDraft.description };
    }
    if (!audio) return null;
    return { ...common, mode: "emotion", audio_id: audio.id, emotion: emotionDraft.emotion };
  };

  const submit = async () => {
    if (!canSubmit || submitting || isRunning) return;
    const payload = buildPayload();
    if (!payload) return;
    setError("");
    // 提交前资源适配检查（仅本地推理需要；端点不可用时优雅降级，不阻塞提交）
    if (!isOnline) {
      try {
        const pf = await api.preflight({
          model_variant: config.modelVariant,
          task: TASK_FOR_MODE[mode],
          bits: config.bits === "fp32" ? null : Number(config.bits),
          sequential: config.sequential,
        });
        setPreflight(pf);
        if (pf.level === "blocked") {
          setError(`资源检查阻断：${pf.reasons.join("；") || "资源不足，请查看环境检测"}`);
          return;
        }
      } catch {
        /* preflight 不可用：继续提交，由后端最终把关 */
      }
    }
    setSubmitting(true);
    try {
      const j = await api.createJob(payload);
      setJob(null);
      setCurrentResult(null);
      setJobId(j.id);
      setJobPollActive(true);
      setDrawerOpen(true);
      toast("info", isOnline ? "任务已提交，将由远程 AuK 服务生成（队列串行）" : "任务已提交，本机队列串行执行");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSubmitting(false);
    }
  };

  const cancel = () => {
    if (!job) return;
    api.cancelJob(job.id)
      .then((r) => toast("info", r.message ?? "已请求停止，将在当前阶段结束后停止"))
      .catch((e) => setError((e as Error).message));
  };

  const retry = () => {
    if (!job) return;
    api.retryJob(job.id)
      .then((j) => {
        setJob(j);
        setCurrentResult(null);
        setJobId(j.id);
        setJobPollActive(true);
        setDrawerOpen(true);
      })
      .catch((e) => setError((e as Error).message));
  };

  const redoJob = async (j: Job) => {
    if (isRunning || submitting) return;
    setError("");
    setSubmitting(true);
    try {
      const nj = await api.createJob(payloadFromJob(j));
      setJob(null);
      setCurrentResult(null);
      setJobId(nj.id);
      setJobPollActive(true);
      setDrawerOpen(true);
      toast("info", "已按相同参数重新生成");
    } catch (e) {
      toast("error", `重做失败：${(e as Error).message}`);
    } finally {
      setSubmitting(false);
    }
  };

  const runPreflight = async () => {
    setPreflightBusy(true);
    try {
      const pf = await api.preflight({
        model_variant: config.modelVariant,
        task: TASK_FOR_MODE[mode],
        bits: config.bits === "fp32" ? null : Number(config.bits),
        sequential: config.sequential,
      });
      setPreflight(pf);
    } catch (e) {
      toast("error", `资源检查不可用：${(e as Error).message}`);
    } finally {
      setPreflightBusy(false);
    }
  };

  /* ---------------- 键盘：Space 播放/暂停，Cmd+Enter 提交 ---------------- */
  const submitRef = useRef(submit);
  submitRef.current = submit;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || document.querySelector('[role="dialog"]')) return;
      const t = e.target as HTMLElement | null;
      const tag = t?.tagName;
      const role = t?.getAttribute?.("role");
      const typing = tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || !!t?.isContentEditable;
      if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
        e.preventDefault();
        void submitRef.current();
        return;
      }
      if (e.code === "Space" && !typing && tag !== "BUTTON" && tag !== "A" && role !== "button" && role !== "switch" && role !== "checkbox" && role !== "tab") {
        e.preventDefault();
        toggleActive();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  /* ---------------- 模式 Tabs（能力门禁仅约束本地；远程 AuK 全模式放行，能力以远程实际为准） ---------------- */
  const tabItems = MODE_ORDER.map((m) => {
    const c = capFor(caps, m);
    const Icon = MODE_ICONS[m];
    const label = (
      <span className="inline-flex items-center gap-1.5">
        <Icon size={14} aria-hidden />
        {MODE_TITLE[m]}
      </span>
    );
    return {
      key: m,
      label: !isOnline && c.state === "not_supported" ? (
        <Tooltip label={c.note || "当前 MLX 分支不支持该能力"}>{label}</Tooltip>
      ) : label,
      disabled: !isOnline && c.state === "not_supported",
      badge: !isOnline && c.state === "unverified" ? (
        <StatusBadge tone="warn" className="px-1.5 py-0 text-[10px] leading-4">实验性</StatusBadge>
      ) : undefined,
    };
  });

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 overflow-y-auto lg:overflow-hidden">
      {/* 模式切换 + 快捷键提示 */}
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-3">
        <Tabs items={tabItems} value={mode} onChange={(k) => onModeChange(k as StudioMode)} />
        <span className="hidden items-center gap-1.5 text-[11px] text-ink-3 md:inline-flex">
          <Kbd>Space</Kbd> 播放/暂停
          <span className="mx-1" aria-hidden>·</span>
          <Kbd>⌘</Kbd>+<Kbd>↵</Kbd> 生成
        </span>
      </div>

      {/* 全局提示（在线 Provider 不依赖本地模型） */}
      {noMainModel && !isOnline && (
        <div className="shrink-0">
          <InlineNote tone="warn">
            尚未安装就绪的主模型（AuK-Flash / AuK Base），无法生成。
            <Button size="sm" variant="outline" className="ml-2" onClick={() => onNavigate("wizard")}>去安装</Button>
          </InlineNote>
        </div>
      )}
      {capsFailed && (
        <div className="shrink-0">
          <InlineNote>能力清单（/api/capabilities）不可用，已按保守默认显示门禁；情绪编辑等能力标记为实验性。</InlineNote>
        </div>
      )}

      {/* 主音频区：仅需要源音频的模式显示（TTS / 音色设计无需原始音频） */}
      {audioNeeded && (
        <AudioStage
          mode={mode}
          audio={audio}
          waveform={waveform}
          region={mainRegion}
          onRegionChange={setMainRegion}
          onAudioLoaded={loadAudio}
          onReplace={replaceAudio}
          recent={recent}
          onRecentChange={setRecent}
        />
      )}

      {/* 内容编辑 + 生成配置：桌面端各自内部滚动，占满剩余高度 */}
      <div className="grid grid-cols-1 gap-4 lg:min-h-0 lg:flex-1 lg:grid-cols-[minmax(0,1fr)_360px]">
        <div className="min-w-0 lg:min-h-0 lg:overflow-y-auto lg:pr-1">
          {mode === "edit" && (
            <EditPanel
              draft={editDraft}
              onChange={setEditDraft}
              onReset={clearEditDraft}
              region={mainRegion}
              onClearRegion={() => setMainRegion(null)}
              hasAudio={!!audio}
            />
          )}
          {mode === "tts" && (
            <TtsPanel
              draft={ttsDraft}
              onChange={setTtsDraft}
              refAudio={ttsRef}
              onRefUploaded={(a) => {
                setTtsRef(a);
                setTtsDraft((d) => ({ ...d, refAudioId: a.id, refKind: "upload" }));
              }}
              onClearRef={() => {
                setTtsRef(null);
                setTtsDraft((d) => ({ ...d, refAudioId: null }));
              }}
              onModeChange={onModeChange}
              onNavigate={onNavigate}
            />
          )}
          {mode === "design" && <DesignPanel draft={designDraft} onChange={setDesignDraft} />}
          {mode === "timbre" && <TimbrePanel draft={timbreDraft} onChange={setTimbreDraft} hasAudio={!!audio} />}
          {mode === "emotion" && (
            <EmotionPanel draft={emotionDraft} onChange={setEmotionDraft} hasAudio={!!audio} capabilityNote={cap.note} />
          )}
        </div>
        <div className="min-h-0 lg:pr-1">
          <ConfigPanel
            config={config}
            onConfigChange={setConfig}
            providers={providerList ?? []}
            models={effectiveModels}
            modelsError={effectiveModels ? null : modelsError}
            canActivate={!!models}
            settings={settings}
            mode={mode}
            audioDuration={audio?.duration ?? null}
            job={job}
            submitting={submitting}
            canSubmit={canSubmit}
            submitHint={submitHint}
            error={error}
            preflight={preflight}
            preflightBusy={preflightBusy}
            onPreflight={runPreflight}
            onSubmit={submit}
            onCancel={cancel}
            onRetry={retry}
            onNavigate={onNavigate}
          />
        </div>
      </div>

      {/* 结果停靠区：底部常驻，完成时自动展开，内容内部滚动（无需整页下拉） */}
      {(drawerOpen || isRunning || !!currentResult || historyJobs.length > 0) && (
        <ResultsDrawer
          docked
          open={drawerOpen}
          onToggle={() => setDrawerOpen((o) => !o)}
          audio={audio}
          waveform={waveform}
          current={currentResult}
          historyJobs={historyJobs}
          mainRegion={mainRegion}
          onMainRegionChange={setMainRegion}
          crossfadeMs={crossfadeMs}
          busy={isRunning || submitting}
          onRedo={redoJob}
          onNavigate={onNavigate}
        />
      )}
    </div>
  );
}