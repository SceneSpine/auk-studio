import type {
  AudioMeta, Capabilities, Diagnostics, FileRef, InstallPlan, Job, ModelStatus,
  ModelsResponse, Preflight, Provider, ProvidersResponse, ProviderTestResult,
  Settings, SystemInfo, Voice, Waveform,
} from "./types";

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, {
    headers: init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...init,
  });
  if (!r.ok) {
    let detail = `${r.status}`;
    try {
      const j = await r.json();
      const d = j.detail ?? j.message ?? j;
      // 新端点错误为 {code,message,details,trace_id} 对象；旧端点为字符串
      detail = typeof d === "string" ? d : (d?.message ?? JSON.stringify(d));
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return r.json() as Promise<T>;
}

export const api = {
  health: () => req<{ status: string }>("/api/health"),
  system: () => req<SystemInfo>("/api/system"),
  capabilities: () => req<Capabilities>("/api/capabilities"),
  diagnostics: () => req<Diagnostics>("/api/system/diagnostics"),
  preflight: (body: { model_variant: string; task: string; bits?: number | null; sequential?: boolean }) =>
    req<Preflight>("/api/system/preflight", { method: "POST", body: JSON.stringify(body) }),

  /* models */
  modelStatus: () => req<ModelStatus>("/api/model/status"),
  unloadModel: () => req<{ ok: boolean; message: string }>("/api/model/unload", { method: "POST" }),
  models: () => req<ModelsResponse>("/api/models"),
  installPlan: (id: string) => req<InstallPlan>(`/api/models/${id}/install-plan`, { method: "POST" }),
  installModel: (id: string, consentLicenseIds: string[]) =>
    req<Job>(`/api/models/${id}/install`, { method: "POST", body: JSON.stringify({ consent_license_ids: consentLicenseIds }) }),
  verifyModel: (id: string) => req<Job>(`/api/models/${id}/verify`, { method: "POST" }),
  activateModel: (id: string) => req<{ ok: boolean; message: string }>(`/api/models/${id}/activate`, { method: "POST" }),

  /* audio */
  uploadAudio: (file: File, onProgress?: (pct: number) => void) =>
    new Promise<AudioMeta>((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const fd = new FormData();
      fd.append("file", file);
      xhr.open("POST", "/api/audio/upload");
      xhr.upload.onprogress = (e) => e.lengthComputable && onProgress?.(Math.round((e.loaded / e.total) * 100));
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) resolve(JSON.parse(xhr.responseText));
        else {
          try {
            reject(new Error(JSON.parse(xhr.responseText).detail ?? xhr.statusText));
          } catch {
            reject(new Error(xhr.statusText));
          }
        }
      };
      xhr.onerror = () => reject(new Error("网络错误"));
      xhr.send(fd);
    }),
  audioList: () => req<AudioMeta[]>("/api/audio"),
  audioGet: (id: string) => req<AudioMeta>(`/api/audio/${id}`),
  waveform: (id: string) => req<Waveform>(`/api/audio/${id}/waveform`),
  audioDelete: (id: string, force = false) =>
    req<{ ok: boolean }>(`/api/audio/${id}${force ? "?force=true" : ""}`, { method: "DELETE" }),
  audioStreamUrl: (id: string) => `/api/audio/${id}/stream`,

  /* jobs */
  createJob: (body: Record<string, unknown>) => req<Job>("/api/jobs", { method: "POST", body: JSON.stringify(body) }),
  jobs: (status?: string, kind?: string) =>
    req<Job[]>(`/api/jobs?${new URLSearchParams({ ...(status ? { status } : {}), ...(kind ? { kind } : {}) })}`),
  job: (id: string) => req<Job>(`/api/jobs/${id}`),
  jobLogs: (id: string, tail = 300) => req<{ lines: string[]; error: string }>(`/api/jobs/${id}/logs?tail=${tail}`),
  cancelJob: (id: string) => req<{ ok: boolean; state: string; message?: string }>(`/api/jobs/${id}/cancel`, { method: "POST" }),
  retryJob: (id: string) => req<Job>(`/api/jobs/${id}/retry`, { method: "POST" }),
  deleteJob: (id: string) => req<{ ok: boolean }>(`/api/jobs/${id}`, { method: "DELETE" }),
  acceptJob: (id: string, accepted: boolean | null) =>
    req<{ ok: boolean }>(`/api/jobs/${id}/accept`, { method: "POST", body: JSON.stringify({ accepted }) }),
  jobResult: (id: string) => req<{ job: Job; files: FileRef[]; audio: AudioMeta | null }>(`/api/jobs/${id}/result`),
  splice: (id: string, body: Record<string, unknown>) =>
    req<{ file_id: string; url: string; duration: number; sample_rate: number; channels: number }>(
      `/api/jobs/${id}/splice`, { method: "POST", body: JSON.stringify(body) }),
  trim: (id: string, body: Record<string, unknown>) =>
    req<{ file_id: string; url: string; duration: number }>(`/api/jobs/${id}/trim`, { method: "POST", body: JSON.stringify(body) }),

  /* outputs */
  rateOutput: (fileId: string, body: { rating?: number | null; favorite?: boolean }) =>
    req<FileRef>(`/api/outputs/${fileId}/rate`, { method: "POST", body: JSON.stringify(body) }),
  outputUrl: (fileId: string, download = false) => `/api/outputs/${fileId}${download ? "?download=1" : ""}`,

  /* voices */
  voices: (includeArchived = false) => req<Voice[]>(`/api/voices${includeArchived ? "?include_archived=true" : ""}`),
  createVoice: (body: {
    name: string; description?: string; tags?: string[]; audio_id: string;
    consent_confirmed: boolean; allowed_use?: string; source?: string; job_id?: string | null;
  }) => req<Voice>("/api/voices", { method: "POST", body: JSON.stringify(body) }),
  deleteVoice: (id: string) => req<{ ok: boolean }>(`/api/voices/${id}`, { method: "DELETE" }),
  archiveVoice: (id: string, archived: boolean) =>
    req<Voice>(`/api/voices/${id}/archive`, { method: "POST", body: JSON.stringify({ archived }) }),

  /* providers（本地 + 在线 TTS） */
  providers: () => req<ProvidersResponse>("/api/providers"),
  createProvider: (body: { name: string; kind: import("./types").ProviderKind; base_url: string; api_key?: string }) =>
    req<Provider>("/api/providers", { method: "POST", body: JSON.stringify(body) }),
  updateProvider: (id: string, body: Partial<{ name: string; base_url: string; api_key: string; model: string; voice: string; enabled: boolean }>) =>
    req<Provider>(`/api/providers/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  deleteProvider: (id: string) => req<{ ok: boolean }>(`/api/providers/${id}`, { method: "DELETE" }),
  testProvider: (id: string) => req<ProviderTestResult>(`/api/providers/${id}/test`, { method: "POST" }),

  /* settings */
  settings: () => req<Settings>("/api/settings"),
  saveSettings: (v: Partial<Settings>) => req<Settings>("/api/settings", { method: "PUT", body: JSON.stringify(v) }),

  fileUrl: (id: string, download = false) => `/api/files/${id}${download ? "?download=1" : ""}`,
};