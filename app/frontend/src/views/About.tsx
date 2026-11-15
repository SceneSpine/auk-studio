/**
 * 关于：品牌 / 非官方声明（中英）/ 许可证披露 / 能力矩阵摘要 /
 * 快捷键帮助 / 实测使用提示 / 仓库文档 / 技术栈许可。
 */
import { useState } from "react";
import { AlertTriangle, BookOpen, Building2, ExternalLink, FileText, Keyboard, QrCode, Scale, ShieldAlert } from "lucide-react";
import { api } from "../api";
import { BrandMark } from "../components/AppShell";
import {
  Card,
  InlineError,
  InlineNote,
  Kbd,
  PageHeader,
  Skeleton,
  StatusBadge,
} from "../components/ui";
import { usePoll } from "../hooks";
import type { Capabilities, CapabilityState } from "../types";
import { fmtTime } from "../types";

const TASK_LABEL: Record<string, string> = {
  speech_edit: "语音编辑",
  zero_shot_tts: "零样本 TTS",
  instruction_tts: "指令 TTS / 音色设计",
  emotion_edit: "情绪编辑",
  timbre_edit: "音色重塑",
  speech_enhancement: "音频修复（降噪/去混响）",
  source_separation: "说话人 / 源分离",
  asr_alignment: "ASR / 强制对齐",
};

const STATE_META: Record<CapabilityState, { tone: "ready" | "warn" | "unknown"; label: string }> = {
  supported: { tone: "ready", label: "可用（已实测）" },
  unverified: { tone: "warn", label: "未实测 / 实验性" },
  not_supported: { tone: "unknown", label: "不支持" },
};

const DOC_LINKS = [
  { path: "docs/TEST_REPORT.md", desc: "本机实测报告（编辑成功率 / RTF / 内存）" },
  { path: "docs/MODEL_LICENSES.md", desc: "模型与组件许可审查" },
  { path: "docs/API_CONTRACT.md", desc: "前后端 API 契约" },
  { path: "docs/CAPABILITIES.md", desc: "能力门禁说明" },
  { path: "docs/DEPLOYMENT_REPORT.md", desc: "部署与环境报告" },
];

const TECH_STACK = [
  { name: "React 18", license: "MIT", role: "前端界面" },
  { name: "FastAPI", license: "MIT", role: "本地 API 服务" },
  { name: "MLX", license: "MIT", role: "Apple Silicon 推理" },
  { name: "WaveSurfer.js", license: "BSD-3-Clause", role: "音频波形" },
  { name: "Tailwind CSS", license: "MIT", role: "样式" },
  { name: "Vite", license: "MIT", role: "构建" },
  { name: "lucide", license: "ISC", role: "图标" },
];

function ExtLink({ href, children }: { href: string; children: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noreferrer"
      className="inline-flex items-center gap-1 text-brand hover:underline"
    >
      {children}
      <ExternalLink size={12} aria-hidden />
    </a>
  );
}

/**
 * 公司联络二维码（微信联络卡）。
 * 源图：docs/assets/contact-qr.jpg，构建副本：app/frontend/public/contact-qr.jpg。
 * 更换时同步两处即可；加载失败自动回退占位框。
 */
function ContactQR() {
  const [missing, setMissing] = useState(false);
  if (missing) {
    return (
      <div
        className="flex h-44 w-36 flex-col items-center justify-center gap-2 rounded-input border-2 border-dashed border-line bg-subtle text-ink-3"
        role="img"
        aria-label="公司联络二维码（加载失败）"
      >
        <QrCode size={34} strokeWidth={1.5} aria-hidden />
        <span className="text-center text-[11px] leading-4">
          联络二维码
          <br />
          加载失败
        </span>
      </div>
    );
  }
  return (
    <img
      src="/contact-qr.jpg"
      alt="影脉科技（南京）有限公司联络二维码（微信）"
      className="w-36 rounded-input border border-line bg-white object-contain"
      onError={() => setMissing(true)}
    />
  );
}

export default function About() {
  const [tick, setTick] = useState(0);
  const { data: caps, error } = usePoll<Capabilities>(() => api.capabilities(), 60000, true, [tick]);

  const groups: CapabilityState[] = ["supported", "unverified", "not_supported"];

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="关于" description="许可与声明 · 能力边界 · 帮助" />

      <div className="space-y-5">
        {/* 品牌区 */}
        <Card>
          <div className="flex items-center gap-4">
            <BrandMark size={56} />
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xl font-semibold tracking-tight">AuK Studio</span>
                <span className="font-mono text-xs text-ink-3">v0.3.0</span>
                <StatusBadge tone="neutral">Unofficial community project</StatusBadge>
              </div>
              <p className="mt-1 text-[13px] leading-5 text-ink-2">
                Local-first AI 语音工作台 · 推理完全在本机完成 · 数据默认不出机
              </p>
            </div>
          </div>
        </Card>

        {/* 出品方 */}
        <Card title={<span className="flex items-center gap-1.5"><Building2 size={15} aria-hidden /> 出品方 · Author</span>}>
          <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
            <div className="min-w-0 space-y-2.5">
              <div className="text-lg font-semibold tracking-tight">影脉科技（南京）有限公司</div>
              <p className="text-[13px] leading-5 text-ink-2">
                AuK Studio 由影脉科技独立开发与维护 —— 本地优先的 AI 语音工作台，
                让语音编辑与创作完全在你的设备上完成。
              </p>
              <div className="flex flex-wrap gap-1.5">
                <StatusBadge tone="neutral">独立开发</StatusBadge>
                <StatusBadge tone="neutral">本地优先 · 数据不出机</StatusBadge>
                <StatusBadge tone="ready">自研代码 MIT 开源</StatusBadge>
              </div>
            </div>
            <div className="shrink-0 text-center">
              <ContactQR />
              <p className="mt-2 text-[11px] text-ink-3">扫码联系我们</p>
            </div>
          </div>
        </Card>

        {/* 非官方声明（显著） */}
        <Card title={<span className="flex items-center gap-1.5"><ShieldAlert size={15} aria-hidden /> 非官方声明 · Unofficial</span>} className="border-warn/40">
          <div className="space-y-3 text-[13px] leading-5 text-ink-2">
            <p lang="en">
              AuK Studio is an independent, unofficial open-source interface for local AI audio workflows. It is not
              affiliated with or endorsed by Tencent or Alibaba Cloud. Model checkpoints and third-party components are
              governed by their own licenses. The currently required Qwen2.5-Omni-3B encoder is distributed under the
              Qwen Research License, which limits use to non-commercial research/evaluation unless separately licensed.
            </p>
            <p>
              AuK Studio 是独立开发的非官方本地语音工作台，与腾讯或阿里云不存在官方关联或背书。模型与第三方组件按各自许可证授权。
              当前 AuK 依赖的 Qwen2.5-Omni-3B 使用 Qwen Research License，商业使用需另行取得授权。
            </p>
          </div>
        </Card>

        {/* 许可证 */}
        <Card title={<span className="flex items-center gap-1.5"><Scale size={15} aria-hidden /> 许可证与使用限制</span>}>
          <div className="space-y-3">
            <div className="rounded-input border border-line p-3.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[13px] font-semibold">AuK Studio 自研代码</span>
                <StatusBadge tone="ready">MIT</StatusBadge>
              </div>
              <p className="mt-1 text-xs leading-[18px] text-ink-2">
                本项目的界面与 API 代码以 MIT 开源，允许使用、修改与分发（保留版权与许可声明）。
                <b>该许可不涵盖模型权重与第三方依赖。</b>
              </p>
            </div>

            <div className="rounded-input border border-line p-3.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[13px] font-semibold">AuK 源码与权重（Tencent）</span>
                <StatusBadge tone="ready">MIT</StatusBadge>
              </div>
              <p className="mt-1 text-xs leading-[18px] text-ink-2">
                腾讯公开发布的 AuK 训练/推理代码、参数与权重采用 MIT，权重本身允许商用；再分发须保留版权与许可声明。
              </p>
              <p className="mt-1.5 text-xs">
                <ExtLink href="https://github.com/Tencent-Hunyuan/AuK">github.com/Tencent-Hunyuan/AuK</ExtLink>
              </p>
            </div>

            <div className="rounded-input border border-warn/40 bg-warn-tint/40 p-3.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[13px] font-semibold">Qwen2.5-Omni-3B（必需语义编码器）</span>
                <StatusBadge tone="warn" icon={<AlertTriangle size={12} aria-hidden />}>
                  Qwen Research License
                </StatusBadge>
              </div>
              <p className="mt-1 text-xs leading-[18px] text-ink-2">
                <b>仅限非商业研究 / 评估用途</b>（许可 §1.i、§2.a）；商业使用需向阿里云另行申请授权（§2.b）。
                再分发须随附许可副本、修改声明与 Notice 归属。AuK 的 MIT 许可<b>不覆盖</b>该依赖。
              </p>
              <p className="mt-1.5 text-xs">
                <ExtLink href="https://huggingface.co/Qwen/Qwen2.5-Omni-3B/blob/main/LICENSE">
                  huggingface.co/Qwen/Qwen2.5-Omni-3B/blob/main/LICENSE
                </ExtLink>
              </p>
            </div>

            <InlineNote tone="warn">
              <b>同意许可 ≠ 获得商业授权。</b>勾选「我已阅读」只是确认知悉条款，不代表取得商业许可。
              在取得 Qwen 商业授权之前，整套推理链（含本地运行）仅限非商业研究 / 评估用途。
            </InlineNote>
          </div>
        </Card>

        {/* 能力矩阵摘要 */}
        <Card
          title="能力矩阵（实测门禁）"
          action={
            caps ? <span className="text-xs text-ink-3">核验于 {fmtTime(caps.verified_at)}</span> : undefined
          }
        >
          {error && !caps && (
            <InlineError onRetry={() => setTick((t) => t + 1)}>加载能力清单失败：{error}</InlineError>
          )}
          {!caps && !error && (
            <div className="space-y-2.5">
              {[0, 1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-12 w-full" />
              ))}
            </div>
          )}
          {caps && (
            <div className="space-y-4">
              {groups.map((state) => {
                const entries = Object.entries(caps.tasks).filter(([, e]) => e.state === state);
                if (entries.length === 0) return null;
                return (
                  <div key={state}>
                    <div className="mb-2">
                      <StatusBadge tone={STATE_META[state].tone}>{STATE_META[state].label}</StatusBadge>
                    </div>
                    <div className="space-y-2">
                      {entries.map(([key, entry]) => (
                        <div key={key} className="rounded-input border border-line px-3.5 py-2.5">
                          <div className="flex flex-wrap items-center gap-2">
                            <span className="text-[13px] font-medium">{TASK_LABEL[key] ?? key}</span>
                            {entry.models.map((m) => (
                              <span key={m} className="rounded-full bg-subtle px-2 py-0.5 font-mono text-[10.5px] text-ink-2">
                                {m}
                              </span>
                            ))}
                          </div>
                          {entry.note && <p className="mt-1 text-xs leading-[18px] text-ink-3">{entry.note}</p>}
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
              <p className="text-xs leading-[18px] text-ink-3">
                能力以本机实测为准（scripts/verify_capabilities.py 生成）；官方支持某任务 ≠ 当前 MLX 分支可用。
              </p>
            </div>
          )}
        </Card>

        {/* 键盘快捷键 */}
        <Card title={<span className="flex items-center gap-1.5"><Keyboard size={15} aria-hidden /> 键盘快捷键</span>}>
          <ul className="space-y-2.5 text-[13px]">
            <li className="flex items-center justify-between gap-3">
              <span className="text-ink-2">播放 / 暂停（焦点不在文本输入时）</span>
              <Kbd>Space</Kbd>
            </li>
            <li className="flex items-center justify-between gap-3">
              <span className="text-ink-2">提交生成任务</span>
              <span className="flex items-center gap-1">
                <Kbd>⌘</Kbd>
                <span className="text-ink-3">+</span>
                <Kbd>Enter</Kbd>
              </span>
            </li>
            <li className="flex items-center justify-between gap-3">
              <span className="text-ink-2">关闭弹窗</span>
              <Kbd>Esc</Kbd>
            </li>
          </ul>
          <p className="mt-3 text-xs text-ink-3">快捷键在创作工作台与弹窗中可用；Windows / Linux 对应 Ctrl+Enter。</p>
        </Card>

        {/* 使用提示（实测结论） */}
        <Card title="使用提示（本机实测结论）">
          <ul className="list-disc space-y-1.5 pl-5 text-[13px] leading-5 text-ink-2">
            <li><b>指令保持精简</b>：保持类指令叠加过多会让模型忽略编辑；默认只保持音色与情绪，编辑未生效时先精简指令。</li>
            <li><b>整句用「全文替换」</b>：自动采用零样本合成模板，实测整句跟随最好；局部词 / 短语用「台词编辑」。</li>
            <li><b>短语替换不保证一次成功</b>：可换随机种子生成多候选挑选。</li>
            <li><b>精度默认 8-bit</b>：4-bit 会导致中文发音可闻退化（官方结论），不建议使用。</li>
            <li>全文替换后不要附加中文风格指令（会被模型朗读）；音色保持已内置。</li>
          </ul>
        </Card>

        {/* 文档 */}
        <Card title={<span className="flex items-center gap-1.5"><BookOpen size={15} aria-hidden /> 项目文档（位于仓库内）</span>}>
          <ul className="space-y-2">
            {DOC_LINKS.map((d) => (
              <li key={d.path} className="flex flex-col gap-0.5 sm:flex-row sm:items-center sm:gap-3">
                <code className="flex shrink-0 items-center gap-1.5 rounded bg-subtle px-2 py-1 font-mono text-xs text-ink-2">
                  <FileText size={12} aria-hidden /> {d.path}
                </code>
                <span className="text-xs leading-[18px] text-ink-3">{d.desc}</span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-ink-3">以上路径相对仓库根目录，随仓库分发，不是在线链接。</p>
        </Card>

        {/* 技术栈 */}
        <Card title="技术栈与许可">
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-line text-left text-xs text-ink-3">
                  <th className="py-2 pr-3 font-medium">组件</th>
                  <th className="py-2 pr-3 font-medium">许可证</th>
                  <th className="py-2 font-medium">用途</th>
                </tr>
              </thead>
              <tbody>
                {TECH_STACK.map((t) => (
                  <tr key={t.name} className="border-b border-line last:border-0">
                    <td className="py-2 pr-3 font-medium">{t.name}</td>
                    <td className="py-2 pr-3 text-ink-2">{t.license}</td>
                    <td className="py-2 text-ink-2">{t.role}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs leading-[18px] text-ink-3">
            许可以实际安装版本为准；正式发版前将生成完整第三方声明（THIRD_PARTY_NOTICES）与依赖审计。
          </p>
        </Card>

        <p className="pb-2 text-center text-xs text-ink-3">
          AuK Studio · 影脉科技（南京）有限公司 · Unofficial community project · 所有处理都在你的设备上完成
        </p>
      </div>
    </div>
  );
}