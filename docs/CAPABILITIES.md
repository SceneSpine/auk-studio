# 能力矩阵（CAPABILITIES）— MLX 分支实测门禁

> 日期：2026-11-14 · 设备：M5 Pro / 48GB · AuK `feat/mlx-apple-silicon` @ `6943a1e` · MLX 0.32.4
> 原则（PRD §2 能力门禁）：**AuK 官方支持 ≠ MLX 分支支持**。每项能力以本机真实生成 + ASR 客观验证为准。
> 机器可读版本：`config/capabilities.json`（`/api/capabilities` 直接读取）。
> 实测脚本：`scripts/verify_capabilities.py`；原始输出：`data/capability-tests/`。

## 矩阵

| 任务 | 状态 | 模型 | 证据 |
| --- | --- | --- | --- |
| 语音编辑 speech_edit | ✅ supported | flash / base | 30 例回归：Flash 86.7%（词 10/10、整句 10/10、短语 6/10），Base 76.7%（TEST_REPORT §3） |
| 零样本 TTS zero_shot_tts | ✅ supported | flash / base | 全文替换模式即英文 TTS 模板 `Say the following with the same voice: '…'`，整句 10/10 |
| 指令 TTS / 音色设计 instruction_tts | ✅ supported | flash / base | 无参考音频实测：描述「二十多岁女性，活泼开朗…」+ 文本，ASR 逐字匹配，情绪检测 HAPPY 与描述一致（5.5s 生成 7.76s 音频） |
| 音色重塑 timbre_edit | ✅ supported | flash / base | 中文模板实测内容逐字保持；**音色变化本身是主观维度**，需用户试听确认（`timbre_cn.wav`） |
| 情绪编辑 emotion_edit | ⚠️ unverified（实验性） | — | 5 次实测（happy/angry/sad × 中英文模板，seed 42/7）：内容全部保持，但 ASR 情绪检测全部 NEUTRAL，未能客观验证情绪变化。UI 标「实验性」，可试用、不承诺效果 |
| 音频修复 speech_enhancement | ⛔ not_supported | — | MLX 分支未实现降噪/去混响（官方 CUDA 路径能力不代表 MLX 可用） |
| 源分离 source_separation | ⛔ not_supported | — | MLX 分支未实现说话人/源分离 |
| ASR / 强制对齐 asr_alignment | ⛔ not_supported | — | 未集成到工作台（SenseVoiceSmall 仅用于离线验证脚本） |

## 指令模板（实测选定，worker 必须遵循）

| 任务 | 模板 | 依据 |
| --- | --- | --- |
| 局部替换 | `把‘{X}’改成‘{Y}’。` + 最多「保持音色+情绪」 | 保持指令过多会抑制编辑（13.3% 教训） |
| 整句替换 / 零样本 TTS | `Say the following with the same voice: '{text}'` | 中文内容编辑模板整句 0/10；英文 TTS 模板 10/10 |
| 指令 TTS（无参考） | `Based on the following description: "{desc}", generate speech content "{text}".` | 官方 Cookbook §1.2 + 本机实测通过 |
| 音色重塑 | `请将这段音频的音色修改为符合以下描述的声音：“{desc}”。` | 中文模板实测内容保持（英文模板亦通过，中文优先） |
| 情绪编辑（实验性） | `将情感转变为{emotion}。` | 官方 Cookbook §4.1；本机未客观验证 |

**已知陷阱**（TEST_REPORT §3.2–3.4）：
- TTS 英文模板后**不可**附加中文风格指令（会被模型朗读出来）。
- 全文/零样本模式目标时长按 `len(text)/4 + 0.5` 估算且 ≥ 源时长。
- 短语替换存在模型能力边界（时间词锚定强），对策：换种子多候选 / Base 备选。

## 前端展示规则

- `supported` → 「可用」，正常入口。
- `unverified` → 「实验性」徽章 + 说明文字，可提交但明示不承诺效果。
- `not_supported` → 「不支持」，入口禁用并说明原因（MLX 分支未实现），**不做假按钮**。
- 模型未安装 → 「需要安装」，直达安装向导。

## 待核验 / 后续

- Base 变体的 instruct_tts / timbre_edit 未单独实测（API 同构，标 supported 依据 Flash 实测 + 官方同架构；如 Base 实测失败应降级）。
- 情绪编辑需主观试听评分（SCORESHEET）或更强情绪源对照后再决定是否升级 supported。
- 4-bit 量化官方明确不建议（中文退化），UI 不提供 4-bit 选项。
## Provider 维度（v0.3）

- 上表门禁针对**本地 MLX 后端**。远程 AuK provider（auk_remote）与本地能力一致：
  - 远程：全部 7 模式（replace/full/custom/tts/instruct_tts/timbre/emotion），能力以远程服务实际为准。
  - 远程任务不做本机能力门禁（门禁是 MLX 实测概念）；UI 对远程不做本地门禁，失败由远程返回兜底。
- 默认 provider 永远为 local；远程为显式 opt-in，音频与文本出机需界面显著提示。AuK Studio 不接其他 TTS 格式（AuK 专用）。
