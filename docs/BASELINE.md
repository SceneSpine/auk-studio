# 基线记录（BASELINE）— AuK Studio 升级前

> 日期：2026-11-14 · 设备：MacBook Pro M5 Pro / 48GB / macOS 26.5.1
> 目的：在增量改造前固定现有可工作链路的真实基线，供回归对照。

## 1. 代码与环境基线

| 项 | 值 |
| --- | --- |
| 升级前版本 | AuK Local Studio v1.0（升级前本地开发基线） |
| 后端 | FastAPI + SQLite(WAL) + 独立推理 worker（`app/backend/`，约 1500 行） |
| 前端 | React 18 + Vite 5 + Tailwind 4 + WaveSurfer 7（`app/frontend/`，约 1700 行） |
| Python | 3.10.22（`.venv-auk`，`config/requirements-lock.txt`） |
| 上游 | Tencent-Hunyuan/AuK `feat/mlx-apple-silicon` @ `6943a1e`（MLX 分支，未合并 main） |
| MLX | 0.32.4 · Device(gpu,0) · Metal 可用 |
| 服务 | 127.0.0.1:7860（仅 localhost），worker 由后端 lifespan 监管 |

## 2. 模型基线（绝不重复下载）

| 组件 | 位置 | 状态 |
| --- | --- | --- |
| AuK-Flash 原始权重 | `models/auk-flash/`（6.76GB，HF sha256 全通过） | ✓ 已安装 |
| AuK Base 原始权重 | `models/auk-base/` | ✓ 已安装 |
| Qwen2.5-Omni-3B | `models/qwen-thinker/`（11.99GB，Research License） | ✓ 已安装 |
| MLX 转换产物 | `models/mlx-converted/`（VAE 587MB / DiT-flash 6122MB / Thinker 14.89GB + q8 副本） | ✓ 已转换 |
| Base MLX 产物 | `models/mlx-converted/dit_base*` / `fusion_base*` | ✓ 已转换 |

## 3. 真实任务基线（升级前旧代码，Web API 实测）

任务：`data/test-set/01-normal.wav`（6.0s 合成男声）局部替换「会议室 → 发布会」，
指令 `把‘会议室’改成‘发布会’。 尽可能保持原音色和原始情绪。`，Flash / 8-bit / seed=42。

| 指标 | 值 |
| --- | --- |
| job_id | `job_918e897282b4` |
| 状态 | completed |
| 端到端耗时 | 6.54s（含模型复用） |
| RTF | 0.998 |
| 峰值 RSS | 5.46 GB |
| 输出时长 | 6.0s |
| 上传→完成 wall | 7.1s |

原始记录：`data/capability-tests/baseline.json`。

## 4. 既有功能清单（回归必须保留）

- 上传 WAV/MP3/M4A/FLAC/OGG/AAC/AIFF/MP4（ffmpeg 回退解码），24kHz mono 标准化，原始文件只读
- 波形峰值预览 + Range 流式播放（206）
- 三种编辑模式：局部替换 / 全文替换（英文 TTS 模板）/ 自定义指令
- 参数：flash/base、bits(None/4/8)、sequential、seed、gen_seconds、nfe(base)
- 任务状态机 + 阶段日志 + 取消（阶段边界）+ 重试 + 崩溃恢复（interrupted→failed 可重试）
- 结果 A/B、接受标记、候选/拼接/片段三种下载
- 拼接导出：未修改区域保留原始 PCM（单元测试 max diff 0.0）、raised-cosine 交叉淡化
- 模型卸载 / 空闲自动卸载（900s）/ 内存压力护栏（level≥4 暂停）
- 历史持久化（重启可查）、深浅主题、设置
- 既有验收：UI 自动化 12/12、中文编辑 Flash 86.7% / Base 76.7%（docs/TEST_REPORT.md）

## 5. 升级约束

1. 不覆盖 `data/`（studio.db、uploads、outputs、jobs、测试集）；数据库迁移只增不删。
2. 不重复下载/转换已存在权重；安装管理器必须先探测复用。
3. 旧 API 路径与响应结构保持兼容（前端整体重构，后端增量扩展）。
4. 所有新能力以 `config/capabilities.json` 实测门禁为准（见 docs/CAPABILITIES.md）。