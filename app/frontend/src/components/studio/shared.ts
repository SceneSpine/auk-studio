/** Studio 各面板共享的草稿类型、默认值与指令模板（实测结论见 docs/CAPABILITIES.md）。 */
import type { Capabilities, CapabilityEntry, Job } from "../../types";
import type { StudioMode } from "../AppShell";

/* ---------------- 台词编辑 ---------------- */

export type EditSub = "replace" | "full" | "custom";
export type StyleKey = "timbre" | "emotion" | "prosody" | "pause";

export interface EditDraft {
  sub: EditSub;
  segOriginal: string;
  segReplacement: string;
  originalText: string;
  targetText: string;
  customInstruction: string;
  extraInstruction: string;
  styles: Record<StyleKey, boolean>;
}

/** 风格指令 chips：默认只勾「保持音色 + 保持情绪」（保持指令过多会抑制编辑，实测 13.3% 教训） */
export const STYLE_CHIPS: { key: StyleKey; label: string; text: string }[] = [
  { key: "timbre", label: "保持音色", text: "尽可能保持原说话人的音色和身份特征。" },
  { key: "emotion", label: "保持情绪", text: "保持原始情绪。" },
  { key: "prosody", label: "保持语速", text: "保持原始语速、语调、重音和表演节奏。" },
  { key: "pause", label: "保持停顿", text: "保持原有停顿和呼吸。" },
];

export const EDIT_DEFAULTS: EditDraft = {
  sub: "replace",
  segOriginal: "",
  segReplacement: "",
  originalText: "",
  targetText: "",
  customInstruction: "",
  extraInstruction: "",
  styles: { timbre: true, emotion: true, prosody: false, pause: false },
};

export function editExtraText(d: EditDraft): string {
  const parts = STYLE_CHIPS.filter((c) => d.styles[c.key]).map((c) => c.text);
  if (d.extraInstruction.trim()) parts.push(d.extraInstruction.trim());
  return parts.join(" ");
}

/** 指令预览（与后端 build_instruction 模板一致） */
export function editInstructionPreview(d: EditDraft): string {
  if (d.sub === "custom") return d.customInstruction.trim();
  if (d.sub === "full") {
    // 整句用零样本 TTS 英文模板；不附加中文风格指令（会被模型朗读——实测 bug）
    return `Say the following with the same voice: '${d.targetText.trim()}'`;
  }
  const base = `把‘${d.segOriginal.trim()}’改成‘${d.segReplacement.trim()}’。`;
  const extra = editExtraText(d);
  return extra ? `${base} ${extra}` : base;
}

/* ---------------- 其余模式草稿 ---------------- */

export interface TtsDraft {
  text: string;
  refKind: "upload" | "voice" | "none";
  voiceId: string | null;
  refAudioId: string | null;
}
export const TTS_DEFAULTS: TtsDraft = { text: "", refKind: "upload", voiceId: null, refAudioId: null };

export interface DesignDraft {
  description: string;
  text: string;
}
export const DESIGN_DEFAULTS: DesignDraft = { description: "", text: "" };

export interface TimbreDraft {
  description: string;
}
export const TIMBRE_DEFAULTS: TimbreDraft = { description: "" };

export interface EmotionDraft {
  emotion: string;
}
export const EMOTION_DEFAULTS: EmotionDraft = { emotion: "" };

export const EMOTIONS = ["开心", "愤怒", "悲伤", "恐惧", "惊讶", "厌恶", "平静", "兴奋"] as const;

/* ---------------- 生成配置 ---------------- */

export interface GenConfig {
  /** 推理 Provider："local" = 内置本地 MLX（默认）；其余为远程 AuK 服务 id（全部模式） */
  providerId: string;
  modelVariant: "flash" | "base";
  bits: "8" | "fp32";
  sequential: boolean;
  seed: string;
  genSeconds: string;
  nfe: string;
}
export const CONFIG_DEFAULTS: GenConfig = {
  providerId: "local",
  modelVariant: "flash",
  bits: "8",
  sequential: false,
  seed: "1",
  genSeconds: "",
  nfe: "32",
};

/** provider_id 是否指向远程 AuK 服务（null/undefined/"local" 均为本地） */
export function isOnlineProvider(id: string | null | undefined): boolean {
  return !!id && id !== "local";
}

/* ---------------- 能力门禁 ---------------- */

export const TASK_FOR_MODE: Record<StudioMode, string> = {
  edit: "speech_edit",
  tts: "zero_shot_tts",
  design: "instruction_tts",
  timbre: "timbre_edit",
  emotion: "emotion_edit",
};

export const MODE_TITLE: Record<StudioMode, string> = {
  edit: "台词编辑",
  tts: "文本转语音",
  design: "音色设计",
  timbre: "音色重塑",
  emotion: "情绪编辑",
};

/** capabilities 端点不可用时的保守默认（与 API_CONTRACT 的缺省策略一致） */
export const FALLBACK_CAPS: Capabilities = {
  backend: "unknown",
  verified_at: 0,
  tasks: {
    speech_edit: { state: "supported", models: ["flash", "base"], note: "能力清单不可用，按保守默认显示为可用。", verified_at: 0 },
    zero_shot_tts: { state: "supported", models: ["flash", "base"], note: "能力清单不可用，按保守默认显示为可用。", verified_at: 0 },
    instruction_tts: { state: "unverified", models: [], note: "能力清单不可用，该能力未经实测确认。", verified_at: 0 },
    timbre_edit: { state: "unverified", models: [], note: "能力清单不可用，该能力未经实测确认。", verified_at: 0 },
    emotion_edit: { state: "unverified", models: [], note: "情绪编辑为实验性功能：未能客观验证情绪变化，可试用，不承诺效果。", verified_at: 0 },
  },
  preferred_templates: {},
};

export function capFor(caps: Capabilities | null, mode: StudioMode): CapabilityEntry {
  const src = caps ?? FALLBACK_CAPS;
  return (
    src.tasks[TASK_FOR_MODE[mode]] ?? { state: "unverified", models: [], note: "无该能力的实测记录。", verified_at: 0 }
  );
}

/* ---------------- 杂项 ---------------- */

/** "auk-flash" / "flash" → "flash" */
export function variantOfModelId(id: string): "flash" | "base" {
  return id.includes("base") ? "base" : "flash";
}

/** 复制参数用的 JSON 摘要（移植旧 Workspace.copyParams 并扩展新模式字段） */
export function jobParamsSummary(job: Job, audioName?: string | null): string {
  return JSON.stringify(
    {
      audio: audioName ?? undefined,
      mode: job.mode,
      segment: job.segment,
      original_text: job.original_text || undefined,
      target_text: job.target_text || undefined,
      instruction: job.final_instruction || job.instruction || undefined,
      description: job.description || undefined,
      emotion: job.emotion || undefined,
      voice_id: job.voice_id ?? undefined,
      provider_id: isOnlineProvider(job.provider_id) ? job.provider_id : undefined,
      model_variant: job.model_variant,
      bits: job.bits,
      sequential: !!job.sequential,
      seed: job.seed,
      gen_seconds: job.gen_seconds,
      nfe: job.nfe,
    },
    null,
    2,
  );
}

/** 由历史任务重建提交参数（重做 = 同参数新任务） */
export function payloadFromJob(job: Job): Record<string, unknown> {
  let segment: { original?: string; replacement?: string } | undefined = job.segment;
  if (!segment && job.segment_json) {
    try {
      segment = JSON.parse(job.segment_json);
    } catch {
      segment = undefined;
    }
  }
  return {
    kind: "infer",
    provider_id: job.provider_id || undefined,
    audio_id: job.audio_id,
    mode: job.mode,
    original_text: job.original_text,
    target_text: job.target_text,
    segment,
    instruction: job.instruction,
    model_variant: job.model_variant,
    bits: job.bits,
    sequential: !!job.sequential,
    seed: job.seed,
    gen_seconds: job.gen_seconds,
    nfe: job.nfe,
    voice_id: job.voice_id ?? undefined,
    description: job.description || undefined,
    emotion: job.emotion || undefined,
  };
}