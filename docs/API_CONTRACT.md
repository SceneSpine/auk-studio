# AuK Studio API 契约（v0.2）

> 后端实现规范 + 前端消费契约。前端类型定义见 `app/frontend/src/types.ts`（已定稿，字段名即 JSON 键名）。
> 原则：旧端点路径与响应**保持兼容**；新端点统一 Pydantic schema；错误统一 `{code, message, details, trace_id}`（HTTPException detail 可为该对象或字符串）。
> 所有文件访问限定 `data/` 内；安装只允许预定义受控操作；默认仅 127.0.0.1。

## 既有端点（保持不变，回归必须通过）

`GET /api/health` · `GET /api/system` · `GET /api/model/status` · `POST /api/model/unload`
`POST /api/audio/upload` · `GET /api/audio` · `GET /api/audio/{id}` · `GET /api/audio/{id}/waveform` · `GET /api/audio/{id}/stream` · `DELETE /api/audio/{id}`
`POST /api/jobs` · `GET /api/jobs` · `GET /api/jobs/{id}` · `GET /api/jobs/{id}/logs` · `POST /api/jobs/{id}/cancel` · `POST /api/jobs/{id}/retry` · `DELETE /api/jobs/{id}` · `POST /api/jobs/{id}/accept` · `GET /api/jobs/{id}/result` · `POST /api/jobs/{id}/splice` · `POST /api/jobs/{id}/trim`
`GET /api/files/{id}` · `GET /api/settings` · `PUT /api/settings`

## 新增端点

### GET /api/capabilities
直接读 `config/capabilities.json`（实测门禁，scripts/verify_capabilities.py 生成）。响应即该文件结构：
`{backend, verified_at, tasks: {<task>: {state: supported|unverified|not_supported, models: [], note, verified_at}}, preferred_templates}`。
文件缺失时返回保守默认（speech_edit/zero_shot_tts supported，其余 unverified）并在 note 说明未实测。

### GET /api/system/diagnostics
真实探针，**观测值与估计值区分**（`measured` 字段）。响应 `Diagnostics`：
- `platform`: chip（`sysctl -n machdep.cpu.brand_string`）、arch、macos、metal（worker_state）、mlx_version、python/uv/ffmpeg/git/node 版本（`--version` 探测，缺失=null）
- `memory`: total_gb、pressure_level（kern.memorystatus_vm_pressure_level）、pressure_label（正常/偏高/严重/不可用）、swap_used_gb/swap_total_gb（`sysctl -n vm.swapusage` 解析）
- `disk`: total/free（shutil.disk_usage）、models_gb/data_gb（du 或 manifest 累计，标注 measured=false 若为估计）
- `checks[]`: 每项 `{id,label,status: ok|warn|fail|unknown,value,detail,suggestion,measured}`。至少覆盖：arch(arm64)、macOS 版本、Metal、MLX 最小张量测试（worker 心跳或缓存结果，不在请求里跑 GPU）、内存压力、Swap、磁盘余量(≥20GB ok / ≥10GB warn / else fail)、ffmpeg、git、uv、模型权重完整性、worker 存活。**每个 warn/fail 必须有 suggestion**。
- `readiness`: `{level: ready|caution|blocked|unknown, reasons[]}` — 综合判定：Metal 不可用或权重缺失→blocked；压力≥2 或磁盘 warn→caution；探针失败→unknown。
- 缓存 5s，避免重复 subprocess。

### POST /api/system/preflight
body `{model_variant, task, bits?, sequential?}` → `Preflight`：
`{level, reasons[], model_loaded, queue_length, disk_free_gb, estimates:{peak_memory_gb|null, rtf_range|null, note}}`。
estimates 只允许来自 docs/TEST_REPORT.md 的**本机实测区间**（Flash 8-bit RTF 0.5–1.0、峰值 ~5.5–7.6GB；Base RTF ~2.0），note 必须注明「本机实测参考，非承诺」。无基准→null。
检查：模型就绪、内存压力、磁盘、队列长度、任务能力（capabilities）。

### GET /api/models
manifest 驱动（新建 `app/backend/model_manager.py` + `config/models_registry.json`）。响应 `{models: ModelInfo[], active: string|null, worker}`。
四个条目：`auk-flash`、`auk-base`（role=main）、`qwen-thinker`、`vae`（role=dependency）。
- state 判定：文件齐全+已转换→ready；原始缺→not_installed；有原始无转换→converting 之外用 not_installed+state_detail 说明；安装任务进行中→downloading/verifying/converting；哈希失败→broken。
- size：download_gb（manifest 原始大小）、converted_gb（MLX 产物）、disk_gb（实际占用，du）。
- license：auk MIT（commercial=true）；qwen-thinker Qwen Research（commercial=false，summary 非商用）；vae 随 Flash MIT。
- memory_fit：48GB→comfortable；按 total_gb 与模型峰值经验推断（≥32GB comfortable，≥16GB tight，else insufficient；非 Apple Silicon→unknown）。
- active：worker_state.model_variant 映射（flash→auk-flash，base→auk-base），未加载时 active=null 但推荐默认 flash。
- depends_on：auk-flash/base → [qwen-thinker, vae]。

### POST /api/models/{id}/install-plan（无副作用）
→ `InstallPlan`。先探测已存在文件（**绝不重复下载**）：
- 已 ready → `already_ready=true`，steps 全为 reuse。
- 否则 steps：download（列出缺失文件、源 URL、大小）→ verify（sha256 对照 config/model_manifest.json）→ convert（auk_mlx.convert 命令）→ quantize（8-bit）→ smoke（可选）。
- `extra_disk_gb` 含转换临时空间；`disk_ok` 对比剩余；`licenses` 列出涉及许可；`requires_consent=true` 当涉及 qwen 或首次安装。
- 下载源 allowlist：ModelScope `Tencent-Hunyuan/AuK-Flash`、`Tencent-Hunyuan/AuK`、`Qwen/Qwen2.5-Omni-3B`；HF 同名（走代理）。复用 scripts/download_models.py 的渠道逻辑。

### POST /api/models/{id}/install
body `{consent_license_ids: string[]}`。未同意所需许可→403 `{code:"license_consent_required"}`。
创建 **kind="install"** 的持久化任务（复用 jobs 队列/日志/取消/重试），worker 串行执行：
download（断点续传，进度写 `install_json`）→ verify → convert（subprocess 受控参数）→ quantize → 完成。
`install_json`: `{phase, downloaded_bytes, total_bytes, files_done, files_total, detail}`。
磁盘不足→任务 failed 明确原因。原始权重只读保护。

### POST /api/models/{id}/verify
创建 kind="verify" 任务：对原始权重逐文件 sha256 对照 manifest，结果写日志与 install_json.detail；不一致→failed 并列出文件。

### POST /api/models/{id}/activate
写 control 标志（新增 activate_variant 列）。worker 在**当前任务结束后**切换/加载；运行中不强制卸载。
响应 `{ok, message}`（如「已请求切换，将在当前任务完成后加载 AuK Base」）。模型未 ready→409。

### 任务扩展（POST /api/jobs）
JobCreate 新增可选字段：`kind`（默认 infer）、`voice_id`、`description`、`emotion`；`audio_id` 对 instruct_tts 可空；mode 扩展为 `replace|full|custom|tts|instruct_tts|timbre|emotion`。
- `tts`：零样本，参考 = audio_id 或 voice_id（解析为音频路径）+ target_text。模板同 full。
- `instruct_tts`：description + target_text，**无参考音频**（engine.generate audio_path=None）。模板 `Based on the following description: "{desc}", generate speech content "{text}".`
- `timbre`：audio_id + description。模板 `请将这段音频的音色修改为符合以下描述的声音：“{desc}”。`
- `emotion`：audio_id + emotion（开心/愤怒/悲伤/恐惧/惊讶/厌恶/平静/兴奋）。模板 `将情感转变为{emotion}。`（实验性）
- gen_seconds 缺省：instruct_tts/tts 按 len(text)/4+0.5（tts 且 ≥源时长）；timbre/emotion 同源时长。
- 能力门禁：capabilities 中 not_supported 的任务→400；unverified 允许但 job 记录 note。
- voice_id 存在时校验音色存在且未归档。
- jobs 表新增列（迁移只增不删）：`kind TEXT DEFAULT 'infer'`、`voice_id TEXT`、`description TEXT DEFAULT ''`、`emotion TEXT DEFAULT ''`、`install_json TEXT DEFAULT ''`。
- GET /api/jobs 支持 `kind` 过滤；列表默认返回全部 kind（前端区分）。

### 输出评分
- `POST /api/outputs/{file_id}/rate` body `{rating?: 1..5|null, favorite?: bool}` → 更新 files 表（新增 rating INTEGER、favorite INTEGER DEFAULT 0），返回 FileRef。
- `GET /api/outputs/{file_id}` → 等同 /api/files/{id}（安全下载/流式）。

### 音色库
- `GET /api/voices?include_archived=` → Voice[]（join audio_files 得 audio 字段）。
- `POST /api/voices` body `{name, description?, tags?, audio_id, consent_confirmed, allowed_use?, source?, job_id?}`。**consent_confirmed 必须 true**（403 otherwise），statement 固定文案「我确认对该参考声音拥有合法使用权，仅在本机用于非商业研究/评估用途」，confirmed_at=now。audio_id 必须存在。
- `DELETE /api/voices/{id}` → 删除记录；**不删除音频文件**（可能被任务引用）；响应说明。
- `POST /api/voices/{id}/archive` body `{archived}` → Voice。
- voices 表：id, name, description, tags_json, audio_id, source, consent_json, allowed_use, job_id, created_at, archived。

### 设置扩展
allowed 集合新增：`language`（默认 zh-CN）、`allow_update_check`（默认 "0"）、`default_variant`（默认 flash）。

## Worker 扩展要点

- install/verify 任务在推理 worker 内串行执行（不与推理并行）；下载用 urllib/requests 流式 + Range 续传，**只允许 allowlist 域名**；convert 用 `[venv_python, -m, auk_mlx.convert, ...]` 参数化 subprocess（cwd=AuK，PYTHONPATH=src），不拼 shell。
- 推理任务：instruct_tts 不传 audio_path；其余同现有链路。峰值 RSS/RTF 记录不变。
- control 表新增 activate_variant；worker 循环在任务间隙消费：与当前 key 不同则 unload+ensure。
- 心跳不变；install 进度经 install_json + stage_detail 暴露。

## 测试要求（tests/api/，pytest + TestClient）

用 `AUK_DATA_DIR`/`AUK_MODELS_DIR` 指向 tmp_path，**不触碰真实 data/ 与 models/**。
覆盖：上传类型/大小/路径穿越、job 校验（各 mode 必填）、能力门禁 400、许可未同意 403、install-plan 复用已存在文件、voices consent 强制、rate 越界、settings 白名单、旧端点回归。
推理 worker 的真实生成测试用 scripts/（已有），不在 pytest 内加载模型。
## Provider 扩展（v0.3：在线 TTS 接入）

### 概念
- `local`：内置本地 MLX 推理（现有行为，默认）。
- 在线 provider：kind="openai_tts"（OpenAI 兼容 /audio/speech 接口）。**仅支持 TTS**（mode=tts）；edit/timbre/emotion/instruct_tts 仍为本地专属。
- 预设：OpenAI（https://api.openai.com/v1）、SiliconFlow（https://api.siliconflow.cn/v1）、自定义。

### providers 表
id, name, kind, base_url, api_key, model, voice, enabled INTEGER DEFAULT 1, created_at。
**api_key 仅存本机 SQLite；任何 API 响应与日志不得出现完整 key**（返回 masked：尾 4 位，如 "sk-…abcd"，has_key: bool）。

### 端点
- GET /api/providers → {providers: Provider[], local: {id:"local", name:"本地 MLX", available: bool}}；Provider={id,name,kind,base_url,model,voice,enabled,has_key,key_masked,created_at}
- POST /api/providers {name,kind,base_url,api_key,model,voice} → Provider（base_url 必须 https 或 http://127.0.0.1|localhost，防 SSRF 到内网任意地址；校验必填）
- PUT /api/providers/{id}（api_key 留空=不修改）→ Provider
- DELETE /api/providers/{id} → {ok}
- POST /api/providers/{id}/test → {ok, latency_ms, error?}：发一条极短 TTS（input="test"）验证连通与鉴权；超时 20s。

### 任务路由
- JobCreate 新增 provider_id（null/"local"=本地）。jobs 表加 provider_id TEXT 列（迁移只增不删）。
- provider_id 在线时：mode 必须 tts（否则 400）；target_text 必填；忽略参考音频/voice_id/bits/seed 等本地参数。
- worker：在线任务调用 POST {base_url}/audio/speech，body {model, input, voice, response_format:"wav"}，Header Bearer key；超时 120s；输出存 data/outputs/{jid}_candidate.wav（若返回 mp3 则存 .mp3 并 probe 元数据）；注册 candidate 文件（audio_id 注册逻辑同 instruct_tts）；记录 elapsed_s；RTF 记 null（非本机推理）；peak_memory_gb null。
- 失败：HTTP 错误/超时 → failed，error 含状态码与服务商消息（**不含 key**）。
- 在线任务不加载本地模型、不占内存护栏；与本地任务仍串行（单 worker）。
- GET /api/jobs 响应含 provider_id；前端据此显示 provider 徽章。

### 隐私
在线任务 = 用户显式选择把文本发送至第三方。UI 必须显著提示目标服务商域名；默认永远 local。
