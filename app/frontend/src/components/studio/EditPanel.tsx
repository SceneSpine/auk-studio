/** 台词编辑面板：局部替换 / 全文重写 / 自由指令（完整移植旧 Workspace 编辑逻辑）。 */
import { RotateCcw } from "lucide-react";
import type { Region } from "../WavePlayer";
import { Button, Card, Collapse, Field, InlineNote, Input, Tabs, Textarea, cn } from "../ui";
import {
  EDIT_DEFAULTS,
  STYLE_CHIPS,
  editInstructionPreview,
  type EditDraft,
  type EditSub,
} from "./shared";

interface Props {
  draft: EditDraft;
  onChange: (v: EditDraft | ((p: EditDraft) => EditDraft)) => void;
  onReset: () => void;
  region: Region | null;
  onClearRegion: () => void;
  hasAudio: boolean;
}

const SUB_TABS: { key: EditSub; label: string }[] = [
  { key: "replace", label: "局部替换" },
  { key: "full", label: "全文重写" },
  { key: "custom", label: "自由指令" },
];

function fmtRegion(s: number): string {
  const m = Math.floor(s / 60);
  const ss = (s % 60).toFixed(1).padStart(4, "0");
  return `${m}:${ss}`;
}

export default function EditPanel({ draft, onChange, onReset, region, onClearRegion, hasAudio }: Props) {
  const set = <K extends keyof EditDraft>(key: K, value: EditDraft[K]) => onChange((d) => ({ ...d, [key]: value }));
  const preview = editInstructionPreview(draft);
  const previewVisible =
    draft.sub === "replace"
      ? draft.segOriginal.trim() !== "" && draft.segReplacement.trim() !== ""
      : draft.sub === "full"
        ? draft.targetText.trim() !== ""
        : draft.customInstruction.trim() !== "";
  const isDefault = JSON.stringify(draft) === JSON.stringify(EDIT_DEFAULTS);

  return (
    <Card
      title="编辑内容"
      action={
        <Button size="sm" variant="ghost" icon={<RotateCcw size={14} />} onClick={onReset} disabled={isDefault} title="清空草稿并恢复默认值">
          恢复默认值
        </Button>
      }
    >
      <div className="space-y-4">
        {!hasAudio && <InlineNote tone="warn">请先在上方上传原始音频，台词编辑需要源音频。</InlineNote>}

        <Tabs
          items={SUB_TABS.map((t) => ({ key: t.key, label: t.label }))}
          value={draft.sub}
          onChange={(k) => set("sub", k as EditSub)}
        />

        {draft.sub === "replace" && (
          <div className="space-y-3">
            <Field label="原片段（要被替换的部分）" required>
              <Input
                value={draft.segOriginal}
                onChange={(e) => set("segOriginal", e.target.value)}
                placeholder="例如：明天的会议"
              />
            </Field>
            <Field label="替换成" required>
              <Input
                value={draft.segReplacement}
                onChange={(e) => set("segReplacement", e.target.value)}
                placeholder="例如：明天的发布会"
              />
            </Field>
            <Collapse title="参考全文（选填，供参考与记录）">
              <Textarea
                rows={2}
                value={draft.originalText}
                onChange={(e) => set("originalText", e.target.value)}
                placeholder="整段对白的逐字稿，首版需手动填写"
              />
            </Collapse>
            <div className="rounded-input border border-line bg-subtle px-3.5 py-2.5 text-xs text-ink-2">
              <span className="font-medium text-ink">时间区域（选填）：</span>
              {region ? (
                <>
                  {fmtRegion(region.start)} – {fmtRegion(region.end)}（{(region.end - region.start).toFixed(2)}s，来自上方波形选区）
                  <button className="ml-2 cursor-pointer text-brand hover:underline" onClick={onClearRegion}>清除</button>
                </>
              ) : (
                <span className="text-ink-3">在上方波形拖拽选择；将作为拼接导出的默认替换区间</span>
              )}
            </div>
          </div>
        )}

        {draft.sub === "full" && (
          <div className="space-y-3">
            <Field label="替换后的完整文本" required hint="整句替换使用零样本 TTS 模板，情绪保持弱于局部编辑">
              <Textarea
                rows={3}
                value={draft.targetText}
                onChange={(e) => set("targetText", e.target.value)}
                placeholder="修改后的完整台词"
              />
            </Field>
            <Collapse title="原始完整文本（选填，供记录）">
              <Textarea
                rows={2}
                value={draft.originalText}
                onChange={(e) => set("originalText", e.target.value)}
                placeholder="原始逐字稿"
              />
            </Collapse>
            <InlineNote>
              全文重写以原音色重新生成目标文本（零样本合成），音色保持已内置；不附加中文风格指令（实测会被模型朗读出来）。如需定制情绪，请用「自由指令」模式。
            </InlineNote>
          </div>
        )}

        {draft.sub === "custom" && (
          <Field label="完整指令（直接发送给模型）" required hint="例如：把‘会议’改成‘发布会’，并用更愤怒的语气。">
            <Textarea
              rows={4}
              value={draft.customInstruction}
              onChange={(e) => set("customInstruction", e.target.value)}
              placeholder="直接描述你想要的编辑效果"
            />
          </Field>
        )}

        {/* 风格指令 chips：仅局部替换模式显示（full/custom 不附加，避免 TTS 模板被朗读 bug） */}
        {draft.sub === "replace" && (
          <div className="space-y-2">
            <div className="text-[13px] font-medium text-ink">风格指令（可多选，附加到编辑指令后）</div>
            <div className="flex flex-wrap gap-1.5">
              {STYLE_CHIPS.map((c) => (
                <button
                  key={c.key}
                  onClick={() => onChange((d) => ({ ...d, styles: { ...d.styles, [c.key]: !d.styles[c.key] } }))}
                  aria-pressed={draft.styles[c.key]}
                  className={cn(
                    "cursor-pointer rounded-full border px-2.5 py-1 text-xs transition-colors",
                    draft.styles[c.key]
                      ? "border-brand bg-brand-tint font-medium text-brand"
                      : "border-line text-ink-3 hover:bg-subtle",
                  )}
                >
                  {c.label}
                </button>
              ))}
            </div>
            <Input
              value={draft.extraInstruction}
              onChange={(e) => set("extraInstruction", e.target.value)}
              placeholder="补充指令，例如：按指定情绪重新表演——更压抑一些"
            />
            <p className="text-xs leading-[18px] text-ink-3">
              实测提示：保持类指令过多会使模型倾向于原样保留而忽略编辑，默认只勾「保持音色 + 保持情绪」。编辑未生效时先精简指令或换用 AuK Base。
            </p>
          </div>
        )}

        {/* 编辑范围预览 */}
        {preview && previewVisible && (
          <div className="rounded-input border border-line bg-subtle p-3 text-xs leading-[18px] text-ink-2">
            <div className="mb-1 font-medium text-ink">指令预览</div>
            {draft.sub === "replace" && draft.segOriginal.trim() && draft.segReplacement.trim() && (
              <div className="mb-1">
                把「<span className="text-err line-through">{draft.segOriginal.trim()}</span>」改成「
                <span className="font-medium text-ok">{draft.segReplacement.trim()}</span>」
              </div>
            )}
            <div className="break-all font-mono text-[11px] text-ink-3">{preview}</div>
          </div>
        )}
      </div>
    </Card>
  );
}