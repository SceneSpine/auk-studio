# 模型与组件授权审查（MODEL_LICENSES）

> 审查时间：2026-11-14。许可证原文均于当日从官方仓库 / HuggingFace 模型卡实际获取。
> **总体结论：本系统完整推理链依赖 Qwen2.5-Omni-3B（Qwen Research License，仅限非商业）。在取得阿里云商业授权前，整套系统只能用于研究/评估/个人非商业用途。商业集成：NEEDS LEGAL REVIEW。**
> 配套文件：软件依赖实测扫描 [DEPENDENCIES_LICENSES.md](DEPENDENCIES_LICENSES.md) · 归属声明 [../THIRD_PARTY_NOTICES.md](../THIRD_PARTY_NOTICES.md) · 发布门禁 [RELEASE_CHECKLIST.md](RELEASE_CHECKLIST.md)。

## 1. AuK 源码

| 项 | 内容 |
| --- | --- |
| 来源 | https://github.com/Tencent-Hunyuan/AuK（feat/mlx-apple-silicon @ 6943a1e） |
| 许可证 | **MIT**（仓库 LICENSE；pyproject.toml `license = MIT`） |
| 商用 | 允许 |
| 再分发 | 允许（保留版权与许可声明） |

## 2. AuK-Flash 权重

| 项 | 内容 |
| --- | --- |
| 模型卡 | https://huggingface.co/tencent/AuK-Flash （ModelScope: Tencent-Hunyuan/AuK-Flash） |
| 许可证 | **MIT**。HF LICENSE 原文明确："refers solely to training code, inference code, **parameters, and weights** made publicly available by Tencent in accordance with MIT" |
| 商用 | 允许（权重本身） |
| 再分发 | 允许（MIT 条件） |

## 3. AuK Base 权重（首版未部署）

| 项 | 内容 |
| --- | --- |
| 模型卡 | https://huggingface.co/tencent/AuK |
| 许可证 | **MIT**（同上，明确覆盖 parameters and weights） |
| 商用 | 允许（权重本身） |

## 4. Qwen2.5-Omni-3B（Thinker 语义编码器，**必需依赖**）

| 项 | 内容 |
| --- | --- |
| 模型卡 | https://huggingface.co/Qwen/Qwen2.5-Omni-3B |
| 许可证 | **Qwen RESEARCH LICENSE AGREEMENT**（Release 2024-09-19；HF 标记 license:other） |
| 授权范围 | 原文 §2："…FOR **NON-COMMERCIAL PURPOSES ONLY**"；§1.i："Non-Commercial shall mean for research or evaluation purposes only" |
| 商用 | **不允许**。原文 §2.b："If you are commercially using the Materials, you shall request a license from us"（需向阿里云申请商业许可） |
| 再分发 | 允许但须：随附许可协议副本、修改文件加显著声明、保留 Notice 署名（"Qwen is licensed under the Qwen RESEARCH LICENSE AGREEMENT, Copyright (c) Alibaba Cloud. All Rights Reserved."） |
| 其他义务 | §4.b：若用其输出训练/改进并分发 AI 模型，须在产品文档显著标注 "Built with Qwen" / "Improved using Qwen"；§4.a 出口管制合规 |
| 集成到商业软件 | **NEEDS LEGAL REVIEW** —— AuK 的 Thinker 条件编码完全依赖该模型（转换后的 thinker 权重是其派生作品，同样受约束） |

**关键提示：不能因为 AuK 源码与权重是 MIT，就推断整条推理链可商用。** MIT 的 AuK 权重 + Research-only 的 Qwen 编码器组合后，系统整体受最严格组件约束。

## 5. 主要软件依赖（推理环境）

> **2026-11-14 更新**：已完成实际安装环境扫描（pip-licenses + license-checker + ffmpeg -buildconf），
> 完整逐项清单与 copyleft/未知项复核见 **[DEPENDENCIES_LICENSES.md](DEPENDENCIES_LICENSES.md)**。
> 结论：运行时树无 GPL/AGPL，自研代码 MIT 可行；LGPL 项（soxr / libsndfile / frozendict）按动态链接披露。

| 组件 | 许可证（实测） | 备注 |
| --- | --- | --- |
| MLX / mlx-metal | **MIT**（实测确认，非 Apache-2.0） | Apple 官方 |
| PyTorch / torchaudio / torchvision | BSD-3 / BSD | 仅转换与 HF processor 间接使用，MLX 推理不用 |
| transformers / safetensors / huggingface-hub / tokenizers | Apache-2.0 | Qwen2_5OmniProcessor 等 |
| qwen-omni-utils | Apache-2.0（实测） | 多模态预处理 |
| soundfile | BSD-3 wrapper + 捆绑 libsndfile（LGPL-2.1） | 音频读写 |
| soxr | **LGPL-2.1-or-later** | 重采样；动态链接、未修改、可替换 |
| frozendict | **LGPL-3.0-only** | einx 传递依赖；纯 Python import |
| certifi | MPL-2.0 | CA 数据束，未修改 |
| FastAPI / Pydantic | MIT | Web 后端 |
| uvicorn / Starlette | BSD-3 | ASGI |
| React / react-dom | MIT | 前端运行时 |
| WaveSurfer.js | **BSD-3-Clause**（实测，非 MIT） | 波形 |
| lucide-react | **ISC** | 图标 |
| Vite / Tailwind CSS | MIT | 仅构建工具，不分发 |
| FFmpeg | LGPL/GPL（依构建；本机 Homebrew 9.0.2 为 GPL 构建） | 仅 subprocess 调用系统二进制，不链接、不随产品分发 |

**开发链警示（不在运行时 lock 中）**：离线 ASR 验证用的 funasr（MIT）引入 **kaldiio 2.18.1，
其随附许可为 NTT 评估专用协议（禁止再分发）**。仅限本机开发验证，严禁打包进任何分发物，
严禁加入运行时依赖。详见 DEPENDENCIES_LICENSES.md §4.1。

## 6. 生成的音频输出

- AuK MIT 许可未对输出主张权利；Qwen Research License 未对推理输出主张著作权，但** outputs 用于商业场景仍受 §2 非商业限制约束**（使用 Materials 的范围包含运行）。
- 用户提供的原始音频版权由用户自行负责；本工具不绕过任何版权保护。
- 界面与文档不得宣称"输出可无条件商用"。

## 7. 尚未确认的问题

- [ ] 阿里云 Qwen 商业许可的申请渠道与条款（如需商用）。
- [ ] 是否存在 Apache-2.0 许可的替代 Thinker 编码器可直接替换（目前官方实现仅支持 Qwen2.5-Omni-3B，README 明确 Qwen3-Omni 不受支持）。
- [ ] 影视对白素材本身的版权/表演者权利（用户侧责任）。

## 8. 对本项目的执行约束

1. 本地个人/研究用途：**允许**，按本方案部署。
2. 商业交付/对外服务：**暂停**，先取得 Qwen 商业授权（NEEDS LEGAL REVIEW）。
3. 再分发本项目打包（含权重）时须随附 Qwen 许可与 Notice 署名。
4. README 与 Web 界面"使用说明"页须包含本节的非商业限制提示。