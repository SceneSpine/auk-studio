# 依赖许可证实际扫描报告（DEPENDENCIES_LICENSES）

> 扫描日期：2026-11-14 · 设备：MacBook Pro M5 Pro / 48GB / macOS 26.5.1
> 方法：**实际安装环境扫描**，非拟选型清单。
> - Python：`.venv-auk/bin/python -m piplicenses --format=markdown --with-urls`（pip-licenses 5.5.5，经 uv 安装）
> - Node：`npx license-checker --summary --production` 与全量 `--csv`（license-checker 25.0.1，app/frontend 实际 node_modules）
> - FFmpeg：本机 `ffmpeg -version` / `-buildconf` 实测
> 工具输出仅作线索；未知/多许可证项已逐一复核 dist-info METADATA 与随附 LICENSE 原文。
> 配套文件：[THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) · [MODEL_LICENSES.md](MODEL_LICENSES.md) · [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)

## 0. 执行结论（先看）

1. **自研代码采用 MIT 可行。** 运行时依赖树中无 GPL/AGPL 组件；copyleft 项仅为 LGPL 动态链接库（soxr / libsndfile / frozendict）与 MPL-2.0 文件级 copyleft（certifi、tqdm 双许可之一），均与 MIT 自研代码兼容，条件是履行披露与归属义务（见 §5）。
2. **最高风险项：kaldiio 2.18.1（开发依赖，非运行时）。** 随附许可证为 **NTT「SOFTWARE LICENSE AGREEMENT FOR EVALUATION」**——仅限内部评估、**禁止再分发、禁止转让**（§4.b）。它由 funasr / modelscope 引入，只用于离线 ASR 验证脚本，**不在 `config/requirements-lock.txt` 运行时清单中**。严禁将其打包进任何分发物；长期建议替换验证工具链（见 §4.1）。
3. **FFmpeg 为系统二进制调用，不链接、不随仓库分发。** 本机 Homebrew 构建为 **GPL-3.0-or-later**（`--enable-gpl --enable-version3 --enable-libx264 --enable-libx265`，无 `--enable-nonfree`）。本项目仅以 subprocess 调用用户自装的 ffmpeg，GPL 不传染自研代码；若未来随产品分发 ffmpeg 二进制，须按 GPL 履行义务（见 §6）。
4. **Node 生产依赖全部宽松许可**（MIT / ISC / BSD-3-Clause）。唯一 UNLICENSED 条目是项目自身 `auk-local-studio`（package.json 未填 license 字段，由仓库根 MIT LICENSE 覆盖；建议维护者在 package.json 补 `"license": "MIT"`）。
5. 需要 NOTICE 归属的主要组件清单见 §5 与 THIRD_PARTY_NOTICES.md。

## 1. 运行时依赖与开发依赖的区分

| 类别 | 定义 | 清单依据 |
| --- | --- | --- |
| **运行时（Web 工作台 + MLX 推理）** | `config/requirements-lock.txt` 所列（82 项，含 editable AuK） | setup.sh 安装 `AuK[mlx]` + fastapi/uvicorn 等 |
| **转换工具链（运行时安装但推理不用）** | torch / torchaudio / torchvision / torchdiffeq 等 | MLX 推理不 import torch；`auk_mlx.convert` 用 torch 读权重，transformers 提供 Qwen processor |
| **开发/验证工具（不在 lock 中）** | funasr 及其依赖链、modelscope、pip-licenses 等 | 仅 scripts/asr_verify.py、run_quality_tests.py 等离线验证使用 |
| **前端运行时（打包进 dist）** | react / react-dom / lucide-react / wavesurfer.js 及其传递依赖 | license-checker --production |
| **前端构建工具（不分发）** | vite / tailwindcss / typescript / esbuild / rollup / lightningcss 等 | license-checker 全量 |

## 2. Python 运行时依赖（config/requirements-lock.txt 对照实际安装）

许可证来自 pip-licenses 实测；SPDX 标识已对多许可项做归一化。

| 包 | 版本 | 许可证 | 用途 / 备注 |
| --- | --- | --- | --- |
| annotated-doc | 0.0.6 | MIT | FastAPI 文档辅助 |
| annotated-types | 0.8.0 | MIT | Pydantic 类型 |
| anyio | 4.16.0 | MIT | 异步基础 |
| audioread | 3.1.0 | MIT | librosa 音频解码 |
| **auk** | 0.1.0 (editable) | **MIT**（Tencent） | 上游 AuK，本地 editable 安装调用，**不复制源码、不再分发**；见 UPSTREAM_AUDIT.md |
| av | 17.1.0 | BSD-3-Clause | PyAV，qwen-omni-utils 媒体解码 |
| **certifi** | 2026.10.23 | **MPL-2.0** | CA 证书数据束；文件级 copyleft，作为数据文件使用无传染，需披露 |
| cffi | 2.1.1 | MIT-0 | soundfile 等 C 绑定 |
| charset-normalizer | 3.5.2 | MIT | requests 依赖 |
| click | 8.5.1 | BSD-3-Clause | uvicorn CLI |
| cloudpickle | 3.1.2 | BSD-3-Clause | 序列化 |
| decorator | 5.3.1 | BSD-2-Clause | librosa 依赖 |
| einops | 0.8.2 | MIT | AuK 张量重排 |
| einx | 0.4.3 | MIT | x-transformers 依赖 |
| exceptiongroup | 1.3.1 | MIT | anyio backport |
| **fastapi** | 0.162.5 | **MIT** | Web 后端框架 |
| filelock | 4.1.0 | MIT | torch/HF 缓存锁 |
| **frozendict** | 2.5.1 | **LGPL-3.0-only** ⚠️ | einx 的依赖；纯 Python，import 视为动态链接，见 §5.2 |
| fsspec | 2026.9.0 | BSD-3-Clause | 文件系统抽象 |
| h11 | 0.16.0 | MIT | uvicorn HTTP 协议 |
| hf-xet | 1.8.0 | Apache-2.0 | HF 下载加速 |
| httptools | 0.9.0 | MIT | uvicorn 解析器 |
| huggingface-hub | 0.36.2 | Apache-2.0 | processor/下载 |
| idna | 3.20 | BSD-3-Clause | 域名编码 |
| inquirerpy | 0.3.4 | MIT | AuK CLI 交互 |
| jinja2 | 3.1.6 | BSD-3-Clause | 模板（torch/transformers） |
| joblib | 1.6.0 | BSD-3-Clause | librosa/sklearn |
| lazy-loader | 0.6 | BSD-3-Clause | 延迟导入 |
| librosa | 0.11.0 | ISC | 音频特征 |
| llvmlite | 0.50.0 | BSD-2-Clause AND Apache-2.0 WITH LLVM-exception | numba JIT；宽松 |
| loguru | 0.8.0 | MIT | 后端日志 |
| markupsafe | 3.0.4 | BSD-3-Clause | jinja2 依赖 |
| **mlx** | 0.32.4 | **MIT**（Apple） | 推理框架。注意：是 MIT，**不是** Apache-2.0 |
| mlx-metal | 0.32.4 | MIT | MLX Metal 后端 |
| mpmath | 1.3.0 | BSD-3-Clause | sympy 依赖 |
| msgpack | 1.2.4 | Apache-2.0 | 序列化 |
| networkx | 3.4.2 | BSD-3-Clause | torch 依赖 |
| numba | 0.68.1 | BSD-2-Clause | librosa JIT |
| numpy | 2.2.6 | BSD-3-Clause | 数值基础 |
| omegaconf | **2.3.1 安装 / 2.4.0 lock** ⚠️ | BSD-3-Clause | AuK 配置；**lock 与实际安装版本不一致**，见 §7 |
| opentelemetry-api | 1.45.2 | Apache-2.0 | fastapi/starlette/transformers 的可选传递依赖；**仅 API 包，未安装 SDK/exporter，应用代码 0 处引用，不构成遥测** |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause | 版本解析（双许可，任选） |
| pfzy | 0.3.4 | MIT | inquirerpy 模糊匹配 |
| pillow | 12.3.0 | MIT-CMU（HPND） | 图像（qwen-omni-utils/torchvision） |
| platformdirs | 4.12.4 | MIT | pooch 缓存目录 |
| pooch | 1.9.0 | BSD-3-Clause | librosa 示例数据 |
| prompt-toolkit | 3.0.53 | BSD-3-Clause | inquirerpy 依赖 |
| pycparser | 3.11 | BSD-3-Clause | cffi 依赖 |
| **pydantic** | 2.14.3 | **MIT** | API schema |
| pydantic-core | 2.50.4 | MIT | pydantic 核心 |
| pysocks | 1.7.1 | BSD | SOCKS 代理 |
| python-dotenv | 1.2.4 | BSD-3-Clause | .env 配置 |
| python-multipart | 0.0.32 | Apache-2.0 | 文件上传解析 |
| pyyaml | 6.0.3 | MIT | YAML 配置 |
| qwen-omni-utils | 0.0.9 | Apache-2.0 | Qwen 多模态预处理 |
| regex | 2026.9.29 | Apache-2.0 AND CNRI-Python | transformers 分词；CNRI 为宽松许可 |
| requests | 2.34.2 | Apache-2.0 | HTTP 客户端 |
| safetensors | 0.8.0 | Apache-2.0 | 权重格式 |
| scikit-learn | 1.7.2 | BSD-3-Clause | librosa 依赖 |
| scipy | 1.15.3 | BSD-3-Clause | DSP |
| **soundfile** | 0.14.0 | BSD-3-Clause（wrapper）**+ 捆绑 libsndfile（LGPL-2.1）** ⚠️ | 音频读写；`_soundfile_data/libsndfile_arm64.dylib` 随附 COPYING，见 §5.2 |
| **soxr** | 1.1.0 | **LGPL-2.1-or-later** ⚠️ | 重采样；`soxr_ext.so` 内建 libsoxr，见 §5.2 |
| starlette | 1.7.0 | BSD-3-Clause | FastAPI 基础 |
| sympy | 1.14.0 | BSD-3-Clause | torch 依赖 |
| threadpoolctl | 3.8.0 | BSD-3-Clause | sklearn 线程控制 |
| tokenizers | 0.22.2 | Apache-2.0 | Qwen tokenizer |
| **torch** | 2.7.1 | BSD-3-Clause | **仅权重转换与 HF processor 间接使用；MLX 推理不用** |
| torch-einops-utils | 0.2.6 | MIT | x-transformers 依赖 |
| **torchaudio** | 2.7.1 | BSD-3-Clause | 转换/processor 链 |
| torchdiffeq | 0.2.5 | MIT | AuK 基础依赖（CUDA 路径用，MLX 不调用） |
| torchvision | 0.22.1 | BSD-3-Clause | AuK 基础依赖（MLX 推理不调用） |
| tqdm | 4.70.1 | MPL-2.0 AND MIT（双许可，**按 MIT 使用**） | 进度条 |
| **transformers** | 4.57.6 | Apache-2.0 | Qwen2_5OmniProcessor |
| typing-extensions | 4.16.0 | PSF-2.0 | typing backport；宽松 |
| typing-inspection | 0.4.5 | MIT | pydantic 依赖 |
| urllib3 | 2.8.0 | MIT | requests 依赖 |
| uvicorn | 0.54.0 | BSD-3-Clause | ASGI 服务器 |
| uvloop | 0.23.0 | Apache-2.0 OR MIT（双许可） | 事件循环 |
| watchfiles | 1.3.0 | MIT | uvicorn 热重载 |
| **wcwidth** | 0.9.4 | MIT | prompt-toolkit 依赖。**pip-licenses 输出遗漏**（METADATA 无 License 字段），已按 dist-info classifier `License :: OSI Approved :: MIT License` 人工补录 |
| websockets | 16.1.1 | BSD-3-Clause | uvicorn WebSocket |
| x-transformers | 2.31.20 | MIT | AuK DiT 组件 |

## 3. Node 依赖（app/frontend 实际 node_modules）

### 3.1 生产依赖（打包进 dist，随前端分发）

| 包 | 版本 | 许可证 |
| --- | --- | --- |
| react | 18.3.1 | MIT |
| react-dom | 18.3.1 | MIT |
| scheduler | 0.23.2 | MIT |
| loose-envify | 1.4.0 | MIT |
| js-tokens | 4.0.0 | MIT |
| csstype | 3.2.3 | MIT |
| **lucide-react** | 1.73.0 | **ISC** |
| **wavesurfer.js** | 7.12.12（package.json ^7.8.6） | **BSD-3-Clause** |
| @types/react / @types/prop-types | 18.3.31 / 15.7.15 | MIT（仅类型声明，不进 bundle；license-checker --production 会列出） |
| auk-local-studio（项目自身） | 1.0.0 | UNLICENSED（private:true 未填字段）→ 由仓库根 MIT LICENSE 覆盖 |

**结论：生产 bundle 无 copyleft、无未知项。**

### 3.2 构建/开发工具（不随产品分发）

全量扫描汇总：MIT 74 · ISC 6 · Apache-2.0 3 · MPL-2.0 2 · BSD-3-Clause 2 · CC-BY-4.0 1 · BlueOak-1.0.0 1 · 0BSD 1 · UNLICENSED 1（项目自身）。

| 包 | 许可证 | 说明 |
| --- | --- | --- |
| vite 5.4.21 / @vitejs/plugin-react 4.7.0 / esbuild 0.21.5 / rollup 4.68.3 / postcss 8.5.32 / browserslist 4.29.5 / @babel/* | MIT | 构建链 |
| tailwindcss 4.3.5 / @tailwindcss/node / @tailwindcss/oxide* | MIT | CSS 框架（产物为自研样式，无义务） |
| typescript 5.9.3 | Apache-2.0 | 编译器 |
| **lightningcss 1.33.0 / lightningcss-darwin-arm64** | **MPL-2.0** | Tailwind 4 的 CSS 压缩器，**仅构建时使用**，不分发其源码/二进制；文件级 copyleft 不影响产物 |
| **caniuse-lite 1.0.30001826** | **CC-BY-4.0** | 浏览器兼容数据，构建时使用；若再分发该数据需署名（本项目不分发） |
| detect-libc 2.1.2 / baseline-browser-mapping 2.11.37 | Apache-2.0 | 构建探测 |
| graceful-fs 4.2.12 | BlueOak-1.0.0 | 宽松 |
| tslib 2.8.1 | 0BSD | 宽松 |
| tests/ui：playwright / playwright-core 1.65.0 | Apache-2.0 | 仅 UI 自动化测试 |

## 4. Python 开发/验证工具（不在运行时 lock 中，严禁打包分发）

setup.sh 的运行时安装不包含这些包；它们来自离线验证与下载工具链的额外安装。

| 包 | 版本 | 许可证 | 用途 |
| --- | --- | --- | --- |
| **kaldiio** | 2.18.1 | **NTT 评估专用许可（非 OSI，禁止再分发）** ⚠️⚠️ | funasr/modelscope 依赖；见 §4.1 |
| funasr | 1.4.26 | MIT | 离线 ASR 验证（SenseVoiceSmall，scripts/asr_verify.py） |
| modelscope | 1.40.3 | Apache-2.0 | 下载工具备选 SDK（当前 download_models.py 仅用标准库） |
| modelscope-hub | 0.7.1 | Apache-2.0 | 同上 |
| aliyun-python-sdk-core / -kms | 2.16.1 / 2.16.5 | Apache-2.0 | modelscope/oss2 链 |
| oss2 | 2.19.1 | MIT | 阿里云 OSS（modelscope 链） |
| antlr4-python3-runtime | 4.9.3 | BSD | hydra 链 |
| hydra-core | 1.3.8 | MIT | funasr 配置 |
| omegaconf（funasr 链复用） | 2.3.1 | BSD-3-Clause | 同上 |
| crcmod | 1.7 | MIT | oss2 链 |
| cryptography | 50.0.2 | Apache-2.0 OR BSD-3-Clause | oss2 链 |
| pycryptodome | 4.4.0 | BSD-2-Clause AND Unlicense AND MIT | funasr 链；全宽松 |
| jaconv | 0.5.0 | MIT | funasr 日语文本 |
| jamo | 0.4.1 | Apache-2.0 | funasr 韩文字母 |
| jieba | 0.42.1 | MIT | funasr 中文分词 |
| jmespath | 1.1.0 | MIT | aliyun SDK |
| protobuf | 7.36.2 | BSD-3-Clause | tensorboardX |
| tensorboardX | 2.6.5 | MIT | funasr 日志 |
| tiktoken | 0.14.0 | MIT | funasr 链 |
| sentencepiece | 0.2.3 | Apache-2.0 | funasr 链 |
| torch-complex | 0.4.4 | Apache-2.0 | funasr 链 |
| rapidfuzz | 3.14.5 | MIT | funasr 评测 |
| pynndescent | 0.7.0 | BSD-2-Clause | umap 链 |
| umap-learn | 0.6.0 | BSD-3-Clause | funasr 链 |
| six | 1.17.0 | MIT | 通用 |
| setuptools | 84.2.1 | MIT | 构建工具 |
| pip-licenses | 5.5.5 | MIT | 本次扫描工具（2026-11-14 新增） |
| prettytable | 3.18.0 | BSD-3-Clause | pip-licenses 依赖 |
| tomli | 2.5.0 | MIT | pip-licenses 依赖 |

### 4.1 kaldiio 重点复核（本次扫描最高风险项）

- pip-licenses 报 `UNKNOWN`。复核 `kaldiio-2.18.1.dist-info/LICENSE` 原文：NTT「SOFTWARE LICENSE AGREEMENT FOR EVALUATION」。
- 要点：§1 仅授予**内部测试/分析/评估**用途的免费许可；§4.b **禁止出售、转让、出租、分发或任何形式的再分发**；§8 禁止再许可；§3 NTT 可无通知终止。
- 引入路径：`funasr → kaldiio`、`modelscope → kaldiio`。两者都**不在** `config/requirements-lock.txt`，Web 工作台与 MLX 推理不 import。
- 处置：
  1. 现状可接受——仅本机开发验证使用，不随仓库/Release 分发（仓库不含任何 site-packages）。
  2. **严禁**把含 kaldiio 的环境打包进 Docker/DMG/Release，或把 funasr 加入运行时依赖。
  3. 若未来提供"一键验证"功能，需先替换 ASR 验证方案（如仅用宽松许可的 whisper.cpp 类工具）或取得 NTT 授权。
  4. 在 CONTRIBUTING.md 中明示该边界。

## 5. Copyleft / 多许可证 / 未知项复核汇总

### 5.1 运行时 copyleft 项（LGPL / MPL）

| 项 | 许可证 | 性质 | 与 MIT 自研代码的兼容性 | 义务 |
| --- | --- | --- | --- | --- |
| soxr 1.1.0（内建 libsoxr） | LGPL-2.1-or-later | 原生扩展，Python import 调用（动态链接） | 兼容 | 披露许可、随附 LGPL 文本获取途径、允许用户替换该库（pip 安装即满足） |
| soundfile 0.14.0 捆绑 libsndfile_arm64.dylib | LGPL-2.1（COPYING 已随附） | 动态库 | 兼容 | 同上 |
| frozendict 2.5.1 | LGPL-3.0-only | 纯 Python 模块，import 调用 | 兼容（FSF 对 Python import 的动态链接解释；保守起见按 LGPL 履行义务） | 披露 + 允许替换 |
| certifi | MPL-2.0 | CA 数据束，未修改 | 兼容（文件级 copyleft，不传染独立文件） | 披露；如修改其文件需公开该文件 |
| tqdm | MPL-2.0 AND MIT | 双许可 | 兼容 | **按 MIT 选用**，保留 MIT 声明 |

**运行时树中无 GPL / AGPL / SSPL / 商业限制组件。**（kaldiio 属开发链，见 §4.1。）

### 5.2 LGPL 履行方式（本项目已满足/需保持）

- 不修改 soxr/libsndfile/frozendict 源码，仅 import 调用 → 不触发"修改版公开"义务。
- 用户通过 pip/uv 自行安装这些库（可自由替换版本）→ 满足 LGPL 的"可替换性"要求。
- 在 THIRD_PARTY_NOTICES.md 列明许可证与官方来源链接。
- **若未来改为打包二进制分发（PyInstaller/Docker 等）**：需随附 LGPL 库的目标文件或提供可重链接机制，并重新法务复核。初版不做此类分发。

### 5.3 多许可证（任选其一，均已择宽松侧）

cryptography（Apache-2.0 OR BSD-3，开发链）、packaging（Apache-2.0 OR BSD-2）、uvloop（Apache-2.0 OR MIT）、tqdm（MPL-2.0 AND MIT → MIT）、pycryptodome（BSD-2 AND Unlicense AND MIT，开发链）、llvmlite（BSD-2 AND Apache-2.0 WITH LLVM-exception）、regex（Apache-2.0 AND CNRI-Python）。

### 5.4 未知项复核结果

| 项 | pip-licenses 报告 | 复核结论 |
| --- | --- | --- |
| kaldiio | UNKNOWN | **NTT 评估专用许可**（§4.1），开发链，禁分发 |
| decorator | BSD-2-Clause（URL UNKNOWN） | METADATA 确认 BSD-2-Clause，宽松 |
| modelscope-hub | Apache（URL UNKNOWN） | METADATA `License: Apache-2.0` 确认 |
| wcwidth | **未出现在输出中** | dist-info classifier 确认 MIT，已补录 §2 |
| auk（editable） | MIT（URL UNKNOWN） | 上游 Tencent MIT，本地调用不再分发 |

## 6. FFmpeg（系统二进制，不链接、不分发）

- 本机实测：Homebrew ffmpeg **9.0.2**，`--enable-gpl --enable-version3 --enable-libx264 --enable-libx265 --enable-libsvtav1 --enable-libopus --enable-libmp3lame --enable-libdav1d --enable-libvmaf --enable-libvpx --enable-openssl`，无 `--enable-nonfree` → 该构建整体为 **GPL-3.0-or-later**。
- 本项目用法：后端以 **subprocess 调用系统 ffmpeg 可执行文件**做解码/格式回退（独立进程、管道通信），**不链接 libav\***。GPL 的传染边界止于进程调用，自研代码不受 GPL 约束。
- 仓库与 Release **不分发任何 ffmpeg 二进制**；用户经 Homebrew 等自行安装，其许可义务由该构建的分发者（Homebrew）承担。
- 若未来随产品分发 ffmpeg：GPL 构建需随附完整对应源码与许可文本（或改用 LGPL 构建并满足动态链接义务），届时重新法务复核。
- 文档与 README 已注明"FFmpeg 许可取决于用户本地构建（LGPL/GPL）"。

## 7. 其他卫生问题（需维护者处理，本次审计只读）

1. **omegaconf 版本漂移**：`config/requirements-lock.txt` 记 2.4.0，实际安装 2.3.1。建议重跑 freeze 或核对安装记录，保证 lock 可复现。
2. **lock 文件含本地绝对路径**：`-e file://<项目根目录>/AuK`。发布前应改为相对路径写法（如 `-e ./AuK`）或在发布版 lock 中剔除 editable 行（config/ 属只读审计范围，此处仅记录）。
3. **app/frontend/package.json 无 license 字段**：license-checker 将项目自身报为 UNLICENSED。建议补 `"license": "MIT"`（app/ 属只读审计范围）。
4. `app/frontend/tsconfig.tsbuildinfo` 被 git 跟踪（构建产物，含本地路径信息），建议从跟踪中移除并加入 .gitignore。
5. `docs/ENVIRONMENT_REPORT.md` 含本机绝对路径（发布门禁"无本地绝对路径"项，见 RELEASE_CHECKLIST）。

## 8. 结论：MIT 可行性与 NOTICE 归属

- **自研代码 MIT：可行。** 条件：保持运行时树无 GPL/AGPL；LGPL 库保持动态链接与可替换；kaldiio 永不进入分发物；FFmpeg 保持系统调用。
- **需要 NOTICE 归属的主要组件**（完整清单见 THIRD_PARTY_NOTICES.md）：
  - 上游：Tencent AuK（MIT）、Qwen2.5-Omni-3B（Qwen Research License，非商用，**权重不随仓库分发**）
  - Python：FastAPI、Pydantic、MLX、uvicorn、Starlette（MIT/BSD）；transformers、safetensors、huggingface-hub、tokenizers、qwen-omni-utils（Apache-2.0）；torch/torchaudio/torchvision、numpy、scipy、soundfile（BSD）；soxr、frozendict（LGPL）；librosa（ISC）；certifi（MPL-2.0）
  - Node：React（MIT）、WaveSurfer.js（BSD-3-Clause）、lucide-react（ISC）、Tailwind CSS（MIT，构建工具）
  - 系统：FFmpeg（用户本地构建，LGPL/GPL，不分发）
- **模型许可与代码许可分离**：MIT 仅覆盖自研源码；Qwen Research License 的非商用约束不因代码 MIT 而消除（详见 MODEL_LICENSES.md）。