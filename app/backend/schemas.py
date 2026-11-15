"""新端点 Pydantic schema（与 app/frontend/src/types.ts 字段一一对应）。

响应模型统一 extra="allow"：后端可附加字段而不被过滤，前端按 types.ts 消费。
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="allow")


# ---------------- capabilities ----------------

class CapabilityEntry(_Base):
    state: str = "unverified"
    models: list[str] = Field(default_factory=list)
    note: str = ""
    verified_at: float = 0


class Capabilities(_Base):
    backend: str = "mlx"
    verified_at: float = 0
    tasks: dict[str, CapabilityEntry] = Field(default_factory=dict)
    preferred_templates: dict[str, str] = Field(default_factory=dict)


# ---------------- diagnostics / preflight ----------------

class DiagCheck(_Base):
    id: str
    label: str
    status: str = "unknown"  # ok|warn|fail|unknown
    value: str = ""
    detail: str | None = None
    suggestion: str | None = None
    measured: bool = False


class Readiness(_Base):
    level: str = "unknown"  # ready|caution|blocked|unknown
    reasons: list[str] = Field(default_factory=list)


class DiagPlatform(_Base):
    chip: str = ""
    arch: str = ""
    macos: str = ""
    metal: bool = False
    mlx_version: str | None = None
    python: str = ""
    uv: str | None = None
    ffmpeg: str | None = None
    git: str | None = None
    node: str | None = None


class DiagMemory(_Base):
    total_gb: float = 0
    pressure_level: int = 0
    pressure_label: str = "不可用"
    swap_used_gb: float = 0
    swap_total_gb: float = 0


class DiagDisk(_Base):
    total_gb: float = 0
    free_gb: float = 0
    models_gb: float = 0
    data_gb: float = 0


class Diagnostics(_Base):
    generated_at: float = 0
    overall: str = "unknown"
    platform: DiagPlatform = Field(default_factory=DiagPlatform)
    memory: DiagMemory = Field(default_factory=DiagMemory)
    disk: DiagDisk = Field(default_factory=DiagDisk)
    checks: list[DiagCheck] = Field(default_factory=list)
    readiness: Readiness = Field(default_factory=Readiness)


class PreflightBody(BaseModel):
    model_variant: str = Field("flash", pattern="^(flash|base)$")
    task: str = "speech_edit"
    bits: int | None = None
    sequential: bool = False


class PreflightEstimates(_Base):
    peak_memory_gb: float | None = None
    rtf_range: list[float] | None = None
    note: str = ""


class Preflight(_Base):
    level: str = "unknown"
    reasons: list[str] = Field(default_factory=list)
    model_loaded: bool = False
    queue_length: int = 0
    disk_free_gb: float = 0
    estimates: PreflightEstimates = Field(default_factory=PreflightEstimates)


# ---------------- models ----------------

class ModelLicense(_Base):
    id: str
    name: str
    url: str = ""
    commercial: bool = False
    summary: str = ""


class ModelSource(_Base):
    repo: str
    revision: str = "main"
    urls: list[str] = Field(default_factory=list)


class ModelSize(_Base):
    download_gb: float = 0
    converted_gb: float = 0
    disk_gb: float = 0


class ModelInfo(_Base):
    id: str
    display_name: str
    family: str = ""
    role: str = "main"
    description: str = ""
    source: ModelSource
    license: ModelLicense
    state: str = "not_installed"
    state_detail: str | None = None
    downloaded: bool = False
    converted: bool = False
    quantized: bool = False
    size: ModelSize = Field(default_factory=ModelSize)
    memory_fit: str = "unknown"
    depends_on: list[str] = Field(default_factory=list)
    active: bool = False


class ModelsResponse(_Base):
    models: list[ModelInfo] = Field(default_factory=list)
    active: str | None = None
    worker: dict = Field(default_factory=dict)


class InstallStep(_Base):
    kind: str  # reuse|download|verify|convert|quantize|smoke
    label: str
    detail: str = ""
    size_gb: float | None = None
    source: str | None = None


class InstallPlan(_Base):
    model_id: str
    steps: list[InstallStep] = Field(default_factory=list)
    total_download_gb: float = 0
    extra_disk_gb: float = 0
    disk_free_gb: float = 0
    disk_ok: bool = True
    licenses: list[ModelLicense] = Field(default_factory=list)
    requires_consent: bool = False
    already_ready: bool = False
    warnings: list[str] = Field(default_factory=list)


class InstallBody(BaseModel):
    consent_license_ids: list[str] = Field(default_factory=list)


# ---------------- voices ----------------

class VoiceConsent(_Base):
    confirmed: bool = False
    statement: str = ""
    confirmed_at: float | None = None


class Voice(_Base):
    id: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    audio_id: str
    source: str = "upload"
    consent: VoiceConsent = Field(default_factory=VoiceConsent)
    allowed_use: str = ""
    job_id: str | None = None
    created_at: float = 0
    archived: bool = False
    audio: dict | None = None


class VoiceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    audio_id: str
    consent_confirmed: bool = False
    allowed_use: str = "non-commercial research/evaluation on this device"
    source: str = Field("upload", pattern="^(upload|generated)$")
    job_id: str | None = None


class VoiceArchive(BaseModel):
    archived: bool = True


# ---------------- providers（在线 TTS） ----------------

class Provider(_Base):
    id: str
    name: str
    kind: str = "openai_tts"
    base_url: str
    model: str = ""
    voice: str = ""
    enabled: bool = True
    has_key: bool = False
    key_masked: str = ""
    created_at: float = 0


class LocalProvider(_Base):
    id: str = "local"
    name: str = "本地 MLX"
    available: bool = False


class ProvidersResponse(_Base):
    providers: list[Provider] = Field(default_factory=list)
    local: LocalProvider = Field(default_factory=LocalProvider)


class ProviderTestResult(_Base):
    ok: bool = False
    latency_ms: int | None = None
    error: str | None = None


class ProviderCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    kind: str = Field("openai_tts", pattern="^openai_tts$")
    base_url: str
    api_key: str = ""
    model: str = Field(min_length=1, max_length=200)
    voice: str = Field(min_length=1, max_length=200)


class ProviderUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    kind: str | None = Field(None, pattern="^openai_tts$")
    base_url: str | None = None
    api_key: str | None = None  # 空串/None = 不修改
    model: str | None = Field(None, min_length=1, max_length=200)
    voice: str | None = Field(None, min_length=1, max_length=200)
    enabled: bool | None = None


# ---------------- outputs ----------------

class RateBody(BaseModel):
    rating: int | None = None
    favorite: bool | None = None