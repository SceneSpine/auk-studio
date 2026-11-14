# 发布门禁核查清单（RELEASE_CHECKLIST）

> 依据：开源合规核查门禁（模型许可 / 品牌 / 素材 / 供应链 / 隐私），逐条对应。
> 核查日期：2026-11-14（v0.2 集成完成终检）· 核查方式：实际 git / 文件 / 环境 / UI 自动化检查。
> 状态标记：✅ 已完成 · 🔶 部分完成 · ⬜ 待办（发布前人工）· ⛔ 不适用（当前）
> **结论：代码与文档门禁已满足；剩余 3 项为发布前人工步骤（商标检索、干净机器复现、SBOM/安全扫描），见文末。**

## 一、04 §9 门禁逐条核查

### 1. 仓库中没有 Qwen/AuK 权重、用户录音、日志、token、私钥或本地绝对路径 — ✅

- ✅ `git ls-files` 核对：无 `*.safetensors / *.pt / *.ckpt / *.bin / *.wav / *.mp3 / *.log / *.db`；`.gitignore` 覆盖 `models/ data/ backups/ logs/ AuK/ .env* node_modules/ dist/ screenshots*/ .claude/ tsbuildinfo`。
- ✅ token/私钥扫描无命中。
- ✅ 本地绝对路径已清理：requirements-lock.txt editable 改相对路径、ENVIRONMENT_REPORT/DEPENDENCIES_LICENSES/RELEASE_CHECKLIST 匿名化、tsconfig.tsbuildinfo 移除跟踪。对跟踪文件做用户主目录路径扫描 = 0 命中。

### 2. AuK MIT LICENSE 和所有被复制文件的声明均被保留 — ✅

- 未复制任何上游源码：`AuK/` git-ignore，setup.sh 浅克隆 `feat/mlx-apple-silicon` + editable 安装（THIRD_PARTY_NOTICES §1 记录 revision `6943a1e`）。
- 上游 LICENSE 随模型下载保留（manifest 含 LICENSE 文件）。

### 3. Qwen Research License 非商用限制被清楚披露，未作商业授权承诺 — ✅

- ✅ 文档：README 顶部声明（中英）、LICENSE 范围注记、NOTICE、THIRD_PARTY_NOTICES §2、docs/MODEL_LICENSES.md。
- ✅ 界面（UI 自动化验证）：About 页中英非官方声明 + 三张许可卡（Qwen Research 非商用加粗 + 官方全文链接 + 「同意许可≠获得商业授权」）；Models 页 Qwen 卡红色「Research-only · 非商用」徽章 + 派生作品约束警告；音色库非商用提示。

### 4. 安装器展示真实模型许可链接与所需确认 — ✅（Web 主路径）

- ✅ Web 安装向导 Step3 独立许可确认（LicenseConsent 组件，逐条展示 AuK MIT / Qwen Research 要点 + 官方全文链接，强制勾选「我已阅读并理解上述许可（同意不代表获得商业授权）」，未勾选禁止下一步）；Models 页 InstallPlanDialog 同样强制。后端 403 license_consent_required 双保险。
- ✅ install-plan 展示完整变更计划（复用/下载/校验/转换/量化、空间、来源域名）。
- 🔶 残留：CLI download_models.py 下载前无许可打印（Web 向导为主路径；CLI 为高级用户脚本，README 已指向许可文档）。

### 5. 软件自身 LICENSE、README、NOTICE、THIRD_PARTY_NOTICES 一致 — ✅

- LICENSE（MIT，AuK Studio contributors）、README（双语 + 非官方 + 能力门禁）、NOTICE、THIRD_PARTY_NOTICES、SECURITY、CONTRIBUTING、.github 模板口径一致。
- ✅ package.json 已补 `"license": "MIT"`（name: auk-studio, version 0.2.0）。

### 6. 完成实际 npm / Python / FFmpeg / 图标 / 字体依赖审查 — ✅

- ✅ Python pip-licenses 实测 + Node license-checker 实测，见 docs/DEPENDENCIES_LICENSES.md。
- ✅ FFmpeg 系统二进制 GPL 构建仅 subprocess 调用，不链接不分发；图标 lucide ISC；字体仅系统字体栈引用，未捆绑。
- ⚠️ 重点项已记录：kaldiio（NTT 评估许可，禁分发，仅开发验证链，不在运行时 lock）、soxr/frozendict/soundfile（LGPL，import 调用合规）、certifi（MPL-2.0）。
- ⬜ 发布前建议：pip-audit / npm audit --omit=dev 归档。

### 7. UI 素材全部自有、授权或符合许可要求 — ✅

- ✅ 全部原创：自研 UI kit + design tokens（02 规范配色）、自有声波刻度 logo（inline SVG）、lucide 图标（ISC）；无 BreezeBlue/Specter 素材/文案/排布复制。
- ✅ 自有截图 11 张在 docs/screenshots/（浅深主题、1440/1280、模型/系统/音色库/任务/关于/A-B/授权弹窗），README 已嵌入。

### 8. 对 AuK Studio 名称和 logo 完成商标/项目冲突检索 — ⬜（发布前人工）

- `AuK Studio` 为暂定工作名。发布前需：GitHub 近似项目/组织、npm/PyPI 包名检索；CNIPA/USPTO/EUIPO/WIPO 商标检索（软件、AI 工具类）。必要时改独立品牌 + 副标题 "Unofficial GUI for AuK"。logo 为独立原创设计。

### 9. 提供非官方声明，不暗示腾讯或阿里云背书 — ✅

- ✅ README 顶部 04 §4 推荐文案原文（中英）；UI 侧栏品牌下「Unofficial · Local-first」、About 页完整声明（UI 自动化断言通过）。

### 10. 公共演示数据和测试声音有明确使用权 — ✅（合成素材）

- ✅ 测试集为 AuK-Flash Instruct TTS 合成（非真人录音），位于 git-ignore 的 data/test-set/，不入库。
- 合成输出仍受 Qwen Research License 约束——公开演示仅限非商业场景。

### 11. 安装器不能运行任意 shell；默认 localhost；不收集遥测 — ✅

- ✅ 下载 allowlist 硬编码（ModelScope/HF 官方仓库），HTTPS + 权重 sha256，参数化 subprocess（无 shell 拼接），safetensors 加载（无 pickle）。
- ✅ AUK_HOST 默认 127.0.0.1；SECURITY.md 披露无鉴权本地 API 风险。
- ✅ 无遥测（0 处 analytics 引用；设置中版本检查默认关闭）。
- 🔶 已披露残留：manifest 小文件仅 size 校验；HF 备渠道 socks5h 在纯 urllib 下不可用（ModelScope 主渠道实测可用）。

### 12. 若后续商业化，取得 Qwen 书面许可或换用经授权且技术兼容的方案 — ⛔（当前非商业发布）

- 商业化前必须取得阿里云书面授权或换用经授权且实证兼容的编码器，并重新法务审查。

## 二、任务书 §7 / Sprint 5 补充项

| 项 | 状态 | 说明 |
| --- | --- | --- |
| 不打包 Qwen 权重、不宣称模型可商用 | ✅ | 仓库/Release 不含权重；MIT 模型标可商用、Qwen 标非商用 |
| 发布前扫描 .env/token/用户音频/用户路径 | ✅ | 见门禁 1，0 命中 |
| pytest API 测试套件 | ✅ | **80 passed**（tests/api/，tmp 隔离）：上传校验/路径穿越/各 mode 必填/能力门禁/许可 403/install-plan 复用/voices consent/rate 越界/settings 白名单/diagnostics/preflight/模板/install-verify 执行/旧端点全回归（splice/trim/accept/cancel/retry/Range 206） |
| tsc + UI 自动化 | ✅ | tsc --noEmit 0 错误；tests/ui/studio_test.mjs **35/35**（9 页面导航/真实数据/浅深主题/1440×900+1280×800+窄窗抽屉/上传→真实编辑任务→结果 A/B→下载→音色授权） |
| 真实生成回归 | ✅ | replace 6.9s RTF 0.71 / instruct_tts 3.6s / timbre 8.4s / 设计候选→音色库保存→删除保护 409；worker 崩溃自愈/取消/重试/activate 切换实测 |
| 干净电脑/新用户流程可复现 | 🔶 | setup.sh 已自动克隆上游 + ckpts 符号链接；convert 复用检测；**需在另一台符合条件的 Mac 实际验证** clone→setup→download→convert→start |
| SBOM（CycloneDX/SPDX） | ⬜ | Release 前生成；DEPENDENCIES_LICENSES.md 可作输入 |
| pip-audit / npm audit | ⬜ | 发布前执行并归档 |
| 截图（docs/screenshots/） | ✅ | 11 张自有截图，README 嵌入 |
| 数据迁移安全 | ✅ | 只增不删；真实 DB 副本验证 204 条旧任务完整保留、幂等 |

## 三、剩余待办（发布前人工步骤）

1. **商标/项目名冲突检索**（门禁 8）——AuK Studio 暂定名，必要时改独立品牌。
2. **干净机器复现**——另一台 Apple Silicon Mac 走完整 setup→download→convert→start→首个任务。
3. **SBOM + pip-audit / npm audit**——Release 前生成并归档。
4. （可选增强）CLI 下载器许可打印、小文件 sha256 补全、HF 备渠道 SOCKS 支持。
5. （商业化时）Qwen 书面授权或兼容替代方案 + 法务复审。