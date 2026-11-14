# 部署记录（DEPLOYMENT_REPORT）

> 部署时间：2026-11-14 · 设备：MacBook Pro M5 Pro / 48GB / macOS 26.5.1
> 所有数值均为本机实测，非引用其他设备数据。

## 1. 代码与环境

| 项 | 值 |
| --- | --- |
| AuK 仓库 | Tencent-Hunyuan/AuK |
| 分支 / revision | `feat/mlx-apple-silicon` @ `6943a1e967409e8c73139a7a345f2a611cfb3dd6`（2026-09-13） |
| 克隆方式 | 浅克隆，经用户自设 SOCKS 代理（GitHub 直连不稳定时） |
| Python | 3.10.22（uv 管理，独立 `.venv-auk`） |
| 关键依赖 | mlx 0.32.4 / torch 2.7.1 / transformers 4.57.6 / soundfile 0.14.0 / soxr 1.1.0 / fastapi 0.162.5 |
| 依赖快照 | `config/requirements-lock.txt`（82 包） |
| 安装渠道 | PyPI 清华镜像（直连 PyPI 的 IPv6 连接停滞，镜像正常） |
| MLX 最小测试 | ✓ arm64 / Device(gpu,0) / Metal 可用 / 512×512 matmul 通过 |

## 2. 模型下载（ModelScope 官方渠道 + HF 官方 sha256 校验）

| 仓库 | 文件 | 大小 | sha256 |
| --- | --- | --- | --- |
| tencent/AuK-Flash | auk_flash.safetensors | 6.122 GB | ✓ 通过 |
| tencent/AuK-Flash | vae.safetensors | 0.637 GB | ✓ 通过 |
| Qwen/Qwen2.5-Omni-3B | model-00001-of-00003 | 4.995 GB | ✓ 通过 |
| Qwen/Qwen2.5-Omni-3B | model-00002-of-00003 | 5.000 GB | ✓ 通过 |
| Qwen/Qwen2.5-Omni-3B | model-00003-of-00003 | 1.978 GB | ✓ 通过 |

- 清单：`config/model_manifest.json`（来自 HF 官方 API）。
- 下载器：`scripts/download_models.py`，64MB 分块 × 8 并行，断点续传，失败自动切换 HF 代理备渠道。
- 初期带宽约 2MB/s，后期升至 ~80MB/s；总耗时约 25 分钟。
- ASR 测试模型 SenseVoiceSmall（iic/SenseVoiceSmall，936MB）另存于 `models/asr/`。

## 3. 权重转换（官方 convert.py，一次性）

| 步骤 | 产物 | 实测 |
| --- | --- | --- |
| vae | mlx-converted/vae.safetensors | 611 tensors, 587 MB |
| dit (flash) | dit_flash.safetensors + fusion_flash.safetensors | 417 tensors, 6122 MB |
| thinker | thinker/thinker.safetensors + thinker_config.json | 923 kept / 1621 skipped, 14.89 GB fp32 |
| quantize q8 flash | dit_flash.q8.safetensors | 1.75 GB |
| quantize q8 flash | thinker/thinker.q8.safetensors | 4.21 GB |

与官方 README 公布数值一致。原始权重全部保留。

## 4. CLI 推理实测（官方 demo：英文内容编辑，7s 输出，Flash 4 步）

| 配置 | 加载 | 生成耗时 | RTF | 备注 |
| --- | --- | --- | --- | --- |
| fp32（首次冷启动） | 36.8s | 25.3s | 3.61 | 含 Metal shader 首次编译 |
| fp32（热态） | 3.0s | 8.8s | 1.26 | OS 文件缓存 |
| **8-bit（推荐）** | **3.2s** | **3.8s** | **0.54** | 预量化权重 |
| 8-bit + sequential | 3.3s | 4.3s | 0.61 | 逐栈加载 |

固定 seed=42 精度对比：

| 对比 | 波形相关 | 最大绝对差 |
| --- | --- | --- |
| fp32 vs 8-bit | **0.99764** | — |
| 8-bit vs 8-bit+sequential | **1.0** | **0.0（bit-identical）** |

结论：8-bit 与 fp32 听感等价（官方结论在本机复现），sequential 输出完全一致。**默认采用 8-bit 常驻**；4-bit 未采用（官方明确中文退化）。

注：本机 Flash 8-bit RTF（0.49–0.61）优于官方 M4 Pro 公布区间（0.6–1.8）；fp32 与 8-bit 存在速度差（官方 M4 Pro 上持平），可能与 M5 Pro 带宽/算力特性及 Flash 4 步负载构成有关，如实记录。

## 5. 中文编辑实测

测试集：`scripts/make_test_set.py` 用 AuK-Flash Instruct TTS 合成 10 段中文对白（seed=42，已知逐字稿），含普通/快速/压抑/愤怒/哭腔/耳语/长句/停顿/噪声/背景音乐。合成总耗时 38.3s。

首段中文局部编辑（CLI，8-bit，seed=42）：

- 输入：`明天上午十点，我们在三楼会议室开会，请准时参加。`（6.0s）
- 指令：`把‘会议室’改成‘发布会’。尽可能保持原说话人的音色、情绪和语速。`
- 输出：6.0s @ 24kHz，生成 3.2s，RTF 0.53
- **ASR 验证（SenseVoiceSmall）**：`明天上午10点，我们在三楼发布会开会，请准时参加。` → 替换准确，其余内容保留 ✓

## 6. Web API 全链路实测

上传 → 创建任务 → worker 推理 → 结果下载 → 拼接导出 → 片段导出：

- 任务耗时 6.0s（含首次模型加载），RTF 0.591，worker 峰值 RSS **7.59 GB**
- 候选 ASR 验证：替换准确 ✓
- 拼接导出：未修改区域 PCM 与原始完全一致（单元测试 max diff = 0.0）✓
- Range 流式播放：HTTP 206 ✓
- 排队取消 / 失败重试 / 设置读写 ✓
- 模型缺失时任务优雅失败并给出明确提示 ✓

## 7. 服务与运维

- 启动：`./scripts/start.sh`（前端自动构建，端口占用自动切换，runtime.json 记录实际端口）
- 停止：`./scripts/stop.sh`（SIGINT 优雅退出，worker 释放模型）
- worker 由后端 lifespan 监管：崩溃自动重启（指数退避），启动时遗留运行中任务标记 failed 可重试
- 内存护栏：`kern.memorystatus_vm_pressure_level` ≥ 4 时暂停新任务
- 空闲自动卸载：默认 900s（可配置）
- 监听：仅 127.0.0.1:7860

## 8. 磁盘占用（部署后）

| 目录 | 大小 |
| --- | --- |
| models/auk-flash | 6.3 GB |
| models/qwen-thinker | 11 GB |
| models/mlx-converted | ~26 GB（fp32 + q8） |
| models/asr | ~0.9 GB |
| 合计 | ~44 GB |

## 9. Base 对照模型部署（附加）

- 下载 tencent/AuK（6.76GB，sha256 校验通过）→ models/auk-base，符号链接 AuK/ckpts/AuK。
- Base VAE 与 Flash VAE **sha256 完全一致**，无需重复转换。
- 转换 dit_base（417 tensors, 6122MB）+ fusion_base + q8（1.75GB）。
- Base-32 8-bit 实测：6s 音频 11.8–14.3s（RTF ~2.0），加载 3.2s。
- Web 已支持模型选择（flash/base）与 NFE（16/32/48，base 生效）。

## 10. 指令模板工程（实测驱动的产品修正）

1. 保持类指令过多抑制编辑 → 默认精简为音色+情绪。
2. 整句替换：中文内容编辑模板失败 → 改用官方英文零样本 TTS 模板（全文替换模式），Flash/Base 均成功。
3. TTS 模板后附加中文风格指令会被朗读 → 全文模式不附加风格指令，UI 隐藏相应控件。
4. 全文模式目标时长按文本长度估算（≥源时长），防止长句截断。
详见 TEST_REPORT.md §3。

## 11. 遗留与后续

- [x] 部署验收全部通过（见 TEST_REPORT.md）
- [x] 质量套件（Flash/Base 各 30 任务）与 ASR 客观验证
- [ ] 主观评分（用户试听填写 SCORESHEET.md）
- [ ] 真人录音测试（当前测试集为模型合成，无版权风险；用户可替换）
- [ ] 商业使用需 Qwen 授权（NEEDS LEGAL REVIEW）