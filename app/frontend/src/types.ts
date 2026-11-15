/* AuK Studio 共享 DTO — 与后端 Pydantic schema 对应（docs/API_CONTRACT.md）。 */

export interface AudioMeta {
  id: string;
  original_name: string;
  stored_path: string;
  normalized_path?: string;
  format: string;
  sample_rate: number;
  channels: number;
  bit_depth: number | null;
  duration: number;
  size_bytes: number;
  sha256: string;
  created_at: number;
  waveform?: Waveform;
}

export interface Waveform {
  points: [number, number][];
  duration: number;
  sample_rate: number;
}

export type JobStatus =
  | "queued" | "preparing" | "loading_model" | "processing"
  | "postprocessing" | "completed" | "failed" | "cancelled";

/** 编辑/创作模式（旧三模式保持兼容） */
export type JobMode = "replace" | "full" | "custom" | "tts" | "instruct_tts" | "timbre" | "emotion";
/** 任务大类：推理 / 模型安装 / 模型校验 */
export type JobKind = "infer" | "install" | "verify";

export interface InstallProgress {
  phase: "prepare" | "download" | "verify" | "convert" | "quantize" | "smoke" | "done";
  downloaded_bytes?: number;
  total_bytes?: number;
  files_done?: number;
  files_total?: number;
  detail?: string;
}

export interface Job {
  id: string;
  kind: JobKind;
  audio_id: string | null;
  mode: JobMode;
  original_text: string;
  target_text: string;
  segment_json: string;
  segment?: { original?: string; replacement?: string };
  instruction: string;
  final_instruction: string;
  model_variant: string;
  bits: number | null;
  sequential: number;
  seed: number | null;
  gen_seconds: number | null;
  nfe: number | null;
  voice_id?: string | null;
  model_id?: string | null;
  provider_id?: string | null;
  description?: string;
  emotion?: string;
  install_json?: InstallProgress | null;
  status: JobStatus;
  stage_detail: string;
  error: string;
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
  elapsed_s: number | null;
  output_path: string | null;
  output_duration: number | null;
  accepted: number | null;
  cancel_requested: number;
  peak_memory_gb: number | null;
  rtf: number | null;
  audio?: AudioMeta | null;
  files?: FileRef[];
}

export interface FileRef {
  id: string;
  job_id: string | null;
  audio_id: string | null;
  kind: "upload" | "candidate" | "spliced" | "segment" | "voice_sample";
  path: string;
  label: string;
  created_at: number;
  url?: string;
  exists?: boolean;
  duration?: number;
  sample_rate?: number;
  rating?: number | null;
  favorite?: number;
}

/* ---------------- providers（本地 + 在线 TTS） ---------------- */

/** AuK Studio 是 AuK 专用工作台：本地 MLX（内置）/ 自建远程 AuK Studio / HF Space（Gradio）。 */
export type ProviderKind = "auk_remote" | "hf_space";

export interface Provider {
  id: string;
  name: string;
  kind: ProviderKind;
  base_url: string;
  model: string;
  voice: string;
  enabled: boolean;
  has_key: boolean;
  key_masked: string;
  created_at: number;
}

export interface ProvidersResponse {
  providers: Provider[];
  local: { id: "local"; name: string; available: boolean };
}

export interface ProviderTestResult {
  ok: boolean;
  latency_ms: number | null;
  error?: string;
}

/* ---------------- capabilities ---------------- */

export type CapabilityState = "supported" | "unverified" | "not_supported";

export interface CapabilityEntry {
  state: CapabilityState;
  models: string[];
  note: string;
  verified_at: number;
}

export interface Capabilities {
  backend: string;
  verified_at: number;
  tasks: Record<string, CapabilityEntry>;
  preferred_templates: Record<string, string>;
}

/* ---------------- system diagnostics ---------------- */

export type DiagStatus = "ok" | "warn" | "fail" | "unknown";
export type ReadinessLevel = "ready" | "caution" | "blocked" | "unknown";

export interface DiagCheck {
  id: string;
  label: string;
  status: DiagStatus;
  value: string;
  detail?: string;
  suggestion?: string;
  measured: boolean;
}

export interface Diagnostics {
  generated_at: number;
  overall: ReadinessLevel;
  platform: {
    chip: string;
    arch: string;
    macos: string;
    metal: boolean;
    mlx_version: string | null;
    python: string;
    uv: string | null;
    ffmpeg: string | null;
    git: string | null;
    node: string | null;
  };
  memory: {
    total_gb: number;
    pressure_level: number;
    pressure_label: string;
    swap_used_gb: number;
    swap_total_gb: number;
  };
  disk: { total_gb: number; free_gb: number; models_gb: number; data_gb: number };
  checks: DiagCheck[];
  readiness: { level: ReadinessLevel; reasons: string[] };
}

export interface Preflight {
  level: ReadinessLevel;
  reasons: string[];
  model_loaded: boolean;
  queue_length: number;
  disk_free_gb: number;
  estimates: { peak_memory_gb: number | null; rtf_range: [number, number] | null; note: string };
}

/* ---------------- models ---------------- */

export type ModelState =
  | "ready" | "not_installed" | "awaiting_license" | "downloading"
  | "verifying" | "converting" | "broken" | "incompatible";

export interface ModelLicense {
  id: string;
  name: string;
  url: string;
  commercial: boolean;
  summary: string;
}

export interface ModelInfo {
  id: string;
  display_name: string;
  family: string;
  role: "main" | "dependency";
  description: string;
  source: { repo: string; revision: string; urls: string[] };
  license: ModelLicense;
  state: ModelState;
  state_detail?: string;
  downloaded: boolean;
  converted: boolean;
  quantized: boolean;
  size: { download_gb: number; converted_gb: number; disk_gb: number };
  memory_fit: "comfortable" | "tight" | "insufficient" | "unknown";
  depends_on: string[];
  active: boolean;
}

export interface WorkerState {
  pid?: number;
  heartbeat?: number;
  model_loaded?: number;
  model_variant?: string | null;
  bits?: number | null;
  sequential?: number;
  current_job_id?: string | null;
  load_seconds?: number | null;
  last_error?: string;
  mlx_version?: string;
  metal_available?: number;
  device?: string;
  alive?: boolean;
}

export interface ModelsResponse {
  models: ModelInfo[];
  active: string | null;
  worker: WorkerState;
}

export interface InstallStep {
  kind: "reuse" | "download" | "verify" | "convert" | "quantize" | "smoke";
  label: string;
  detail: string;
  size_gb?: number;
  source?: string;
}

export interface InstallPlan {
  model_id: string;
  steps: InstallStep[];
  total_download_gb: number;
  extra_disk_gb: number;
  disk_free_gb: number;
  disk_ok: boolean;
  licenses: ModelLicense[];
  requires_consent: boolean;
  already_ready: boolean;
  warnings: string[];
}

/* ---------------- voices ---------------- */

export interface Voice {
  id: string;
  name: string;
  description: string;
  tags: string[];
  audio_id: string;
  source: "upload" | "generated";
  consent: { confirmed: boolean; statement: string; confirmed_at: number | null };
  allowed_use: string;
  job_id: string | null;
  created_at: number;
  archived: boolean;
  audio?: AudioMeta;
}

/* ---------------- legacy / misc ---------------- */

export interface ModelStatus {
  variant: string;
  downloaded: boolean;
  converted: boolean;
  quantized_q8: boolean;
  base_ready?: boolean;
  loaded: boolean;
  worker: WorkerState;
  files: Record<string, { exists: boolean; size_gb: number }>;
  license_note: string;
}

export interface SystemInfo {
  platform: { machine: string; system: string; mac_ver: string; processor: string };
  memory: { total_gb: number; pressure_level: number };
  disk: { total_gb: number; free_gb: number };
  worker: WorkerState;
  paths: { data: string; models: string; logs: string };
  inference_backend: string;
}

export interface Settings {
  theme: string;
  crossfade_ms: string;
  default_bits: string;
  default_sequential: string;
  idle_unload_s: string;
  language: string;
  allow_update_check: string;
  default_variant: string;
}

export const STATUS_LABEL: Record<JobStatus, string> = {
  queued: "排队中",
  preparing: "准备中",
  loading_model: "加载模型",
  processing: "推理中",
  postprocessing: "后处理",
  completed: "已完成",
  failed: "失败",
  cancelled: "已取消",
};

export const MODE_LABEL: Record<JobMode, string> = {
  replace: "台词编辑",
  full: "全文替换",
  custom: "自由指令",
  tts: "文本转语音",
  instruct_tts: "音色设计",
  timbre: "音色重塑",
  emotion: "情绪编辑",
};

export const RUNNING: JobStatus[] = ["queued", "preparing", "loading_model", "processing", "postprocessing"];

export function fmtTime(ts: number | null | undefined): string {
  if (!ts) return "—";
  const d = new Date(ts * 1000);
  return d.toLocaleString("zh-CN", { hour12: false });
}

export function fmtDur(s: number | null | undefined): string {
  if (s == null) return "—";
  if (s < 60) return `${s.toFixed(1)}s`;
  return `${Math.floor(s / 60)}m${(s % 60).toFixed(0)}s`;
}

export function fmtBytes(n: number): string {
  if (n > 1e9) return `${(n / 1e9).toFixed(2)} GB`;
  if (n > 1e6) return `${(n / 1e6).toFixed(1)} MB`;
  return `${(n / 1e3).toFixed(0)} KB`;
}

export function fmtAgo(ts: number | null | undefined): string {
  if (!ts) return "—";
  const diff = Date.now() / 1000 - ts;
  if (diff < 60) return "刚刚";
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`;
  return `${Math.floor(diff / 86400)} 天前`;
}