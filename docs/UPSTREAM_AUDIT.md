# 上游核验报告（UPSTREAM_AUDIT）

> 核验时间：2026-11-14。所有结论来自当日实际读取的仓库源码 / README / HF API，非历史教程。

## 1. 仓库与分支

| 项 | 结论 | 依据 |
| --- | --- | --- |
| 官方仓库 | `Tencent-Hunyuan/AuK`（"AuK: An Open-Source Foundational Model for Speech Generation and Editing"） | GitHub API |
| 采用分支 | **`feat/mlx-apple-silicon`** | 分支存在且为 README "Apple Silicon" 章节指向的实现 |
| 采用 revision | `6943a1e967409e8c73139a7a345f2a611cfb3dd6`（2026-09-13，"feat(mlx): native MLX inference backend for Apple Silicon"） | `git log -1` |
| 是否已合并 main | **否**。main 分支 `src/` 下只有 `auk`，无 `auk_mlx` | GitHub API contents?ref=main |
| 其他分支 | dev-wenming、dev-ziyang、feat/PE、feat/local-pe、main | GitHub API branches |
| 克隆方式 | 浅克隆（--depth 1），完整克隆经代理仍中断 | 实际执行记录 |

MLX 后端完全位于 `src/auk_mlx/`，不 import `src/auk/`（README 明示），CUDA 路径不受影响。**未改用 CUDA 方案。**

## 2. 安装方式（当前实际接口）

```bash
uv venv --python 3.10 && source .venv/bin/activate
uv pip install -e ".[mlx]"
```

- Python：`.python-version` = **3.10**；`requires-python = ">=3.10"`。
- `mlx` extra = `mlx>=0.29`、`soundfile`、`soxr`（pyproject.toml 第 75–79 行）。
- 基础依赖仍会安装：torch>=2.7,<2.8 / torchaudio / torchvision（macOS arm64 为 CPU/MPS 构建，**不含 CUDA**）、transformers>=4.52,<5、qwen-omni-utils、omegaconf、torchdiffeq、x_transformers、safetensors。MLX 推理本身不用 torch，但转换脚本 `convert.py` 用 torch 读权重，故保留。
- mlx 当前最新 **0.32.4**（PyPI 查询）；官方验证版本 0.32.2（M4 Pro / macOS 26.4）。
- 入口点（pyproject.toml `[project.scripts]`）：
  - `auk-mlx-infer` = `auk_mlx.cli:main` ← 本项目采用
  - `auk-infer` / `auk-gradio` = CUDA/PyTorch 路径，不用

## 3. 模型仓库与文件（HF API 实测）

| 模型 | HF ID | 许可证 | 关键文件 | 大小 |
| --- | --- | --- | --- | --- |
| AuK-Flash | `tencent/AuK-Flash` | MIT | `auk_flash.safetensors` 6.122 GB；`vae.safetensors` 0.637 GB；`config.yaml` | 6.76 GB |
| AuK Base | `tencent/AuK` | MIT | `auk_base.safetensors`、`vae.safetensors`、`config.yaml` | 首版**不下载** |
| Thinker | `Qwen/Qwen2.5-Omni-3B` | **Qwen Research License（非商用）** | 3 个 safetensors 分片共 11.97 GB + tokenizer/processor/config | 11.99 GB |

**关键结论（方案 §3.2 问题 7）：AuK-Flash 自带独立 `vae.safetensors`，首版无需下载 Base 的任何文件。** CLI `--flash` 读取 `ckpts/AuK-Flash/config.yaml`；VAE 从 `mlx_dir/vae.safetensors` 加载（由 Flash 的 vae 转换而来）。

ModelScope 官方镜像（README 列出，备选下载渠道）：`Tencent-Hunyuan/AuK-Flash`、`Qwen/Qwen2.5-Omni-3B`。

## 4. 转换工具真实接口（src/auk_mlx/convert.py 源码核实）

```bash
export PYTHONPATH=src
python -m auk_mlx.convert vae     <flash>/vae.safetensors         <mlx>/vae.safetensors
python -m auk_mlx.convert dit     <flash>/auk_flash.safetensors   <mlx>/dit_flash.safetensors
python -m auk_mlx.convert thinker <qwen-dir>                      <mlx>/thinker
python -m auk_mlx.convert quantize <mlx> --bits 8 --variant flash
```

- `kind ∈ {vae, dit, thinker, quantize}`；`quantize` 的 `--variant ∈ {base, flash}`，`--bits ∈ {4,8}`，`--group_size` 默认 64。
- `dit` 转换同时输出 `fusion_flash.safetensors`（layer_weights / layer_scale / inv_freq，**Flash 与 Base 不同，不可混用**）。
- `quantize` 从 **仓库根/ckpts/AuK-Flash/config.yaml** 读架构（硬编码相对路径）→ 本项目用符号链接满足。
- 转换输出 fp32：DiT-flash ≈6.1 GB、Thinker ≈14.9 GB、VAE ≈0.6 GB；q8 副本：DiT ≈1.75 GB、Thinker ≈4.21 GB（README 数值，本机实测后更新）。
- 保留原始权重；转换前检查磁盘与内存。

## 5. 推理 CLI 真实参数（src/auk_mlx/cli.py 源码核实）

```
auk-mlx-infer
  --mlx_dir      默认 <repo>/ckpts/mlx
  --config       默认 <repo>/ckpts/{AuK-Flash|AuK}/config.yaml（--flash 切换）
  --qwen_path    默认 <repo>/ckpts/Qwen2.5-Omni-3B（processor/tokenizer 用，需完整快照目录）
  --flash        使用 Flash（固定 4 步，CFG=0，--nfe/--cfg/--sway 被忽略）
  --bits {4,8}   加载时量化 DiT+Thinker；VAE 恒 fp32；缺省 fp32
  --group_size   默认 64
  --sequential   逐栈加载/释放（Thinker→DiT→VAE），峰值内存更低，每次调用重读权重
  --instruction  必填，自然语言指令
  --audio        参考/源音频（任意采样率/声道，内部 mono→24kHz）；缺省为 Instruct TTS
  --gen_seconds  目标时长；有 --audio 时缺省=输入时长
  --nfe          默认 32（Flash 忽略）
  --cfg          默认 2.0（Flash 忽略）
  --sway         默认 -1.0（Flash 忽略）
  --seed         随机种子（支持）
  --output/-o    必填
```

- `--bits`、`--sequential` **确实存在**（方案 §3.2 问题 8 确认）。
- 输出为**整段重生成音频**（不是仅修改片段）；局部拼回由应用层完成（方案 §8）。
- 无 `--unload` 之类 CLI；Python API `AukMLX` 可常驻复用，`engine.vae/dit/thinker=None` + `gc.collect()` + `mx.clear_cache()` 可释放（infer.py `_release`）。

## 6. Python API（后端集成依据，src/auk_mlx/infer.py）

```python
from auk_mlx.infer import AukMLX, GenerateOptions
engine = AukMLX(mlx_dir, config_path, qwen_dir, bits=8, group_size=64, sequential=False)
audio, sr = engine.generate(instruction, audio_path=wav, opts=GenerateOptions(gen_seconds=..., seed=...))
# audio: np.ndarray float32 mono; sr=24000
```

- 非 sequential 模式三栈常驻，适合单 worker 串行复用（48GB 内存充足）。
- `generate` 内部校验 NaN/Inf；Flash 固定 `FLASH_T_GRID` 4 步。
- 参考音频必须传 `audio_path`（HF processor 按路径读取，16kHz mel）。

## 7. 编辑指令模板（docs/COOKBOOK.md §2.1 实测摘录）

- 替换 CN：`把‘{原文}’改成‘{新文}’`；EN：`Replace '{original}' with '{new}'.`
- 插入 CN：`在‘{锚点}’前面加上‘{内容}’` / 后面
- 删除 CN：`删掉‘{内容}’`
- 内容编辑示例 `--gen_seconds 7.0`（目标时长可显式指定）。

## 8. 官方性能与精度指引（docs/MLX.md，M4 Pro 48GB 数据，非本机实测）

- Flash 4 步：4s 音频约 2–7s（RTF 0.6–1.8）；Base 32 步 RTF 4.2–7.3。
- 峰值内存（Base 32 步 6s）：fp32 24.3GB / fp32+seq 15.4GB / 8-bit 9.1GB / 8-bit+seq 6.1GB。
- **官方明确：用 8-bit，避免 4-bit**（4-bit 中文发音可闻退化）；8-bit 与 fp32 波形相关 0.989、ASR 文本一致。
- 量化只省内存不提速（计算受限）；sequential 输出与常驻 bit-identical。
- 官方自测 cookbook 17 例：Flash 15/17 通过、Base 16/17（唯一失败例为模型本身限制，torch 参考同样失败）。

## 9. 本机适配风险与对策

| 风险 | 对策 |
| --- | --- |
| M5 Pro / macOS 26.5.1 未被官方验证过 | 安装后先跑 MLX 最小测试 + 官方 demo 音频 CLI，实测通过再继续 |
| torch 2.7 arm64 wheel 可用性 | uv 安装时验证；转换仅用 torch 读 safetensors |
| HF 下载需代理 | HTTPS_PROXY=socks5h://127.0.0.1:7897 + PySocks；备选 ModelScope 官方渠道；下载后 sha256 校验 |
| 内存压力（系统已有 swap 历史） | 默认 8-bit；任务串行；推理期间采样 memory_pressure |

## 10. 部署阶段回填（2026-11-14 本机实测）

- [x] 本机 MLX/Metal 最小测试：arm64 / mlx 0.32.4 / Device(gpu,0) / Metal 可用 / matmul 通过
- [x] 转换产物：VAE 587MB（611 tensors）、DiT-flash 6122MB（417 tensors）+ fusion、Thinker 14.89GB（923 kept/1621 skipped）、q8 DiT 1.75GB / Thinker 4.21GB —— 与官方公布一致
- [x] 首段中文编辑：CLI 8-bit seed=42，6s 音频生成 3.2s（RTF 0.53），ASR 验证替换准确
- [x] 精度对比（seed=42）：fp32 vs 8-bit 相关 0.99764；8-bit vs sequential bit-identical（max diff 0.0）
- [x] 本机速度：Flash 8-bit RTF 0.49–0.61（7s 输出），优于官方 M4 Pro 区间；fp32 热态 RTF 1.26
- [x] worker 峰值 RSS：7.59GB（8-bit 常驻，含 processor 与音频缓冲）
- 详见 docs/DEPLOYMENT_REPORT.md 与 docs/TEST_REPORT.md