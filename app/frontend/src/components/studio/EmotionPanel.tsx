/** 情绪编辑面板（实验性）：源音频 + 目标情绪（emotion）。 */
import { FlaskConical } from "lucide-react";
import { Card, Field, InlineNote, Select } from "../ui";
import { EMOTIONS, type EmotionDraft } from "./shared";

interface Props {
  draft: EmotionDraft;
  onChange: (v: EmotionDraft | ((p: EmotionDraft) => EmotionDraft)) => void;
  hasAudio: boolean;
  capabilityNote: string;
}

export default function EmotionPanel({ draft, onChange, hasAudio, capabilityNote }: Props) {
  return (
    <Card title="情绪编辑">
      <div className="space-y-4">
        <InlineNote tone="warn">
          <FlaskConical size={13} className="mr-1 inline" aria-hidden />
          实验性功能：{capabilityNote}
        </InlineNote>
        {!hasAudio && <InlineNote tone="warn">请先在上方上传源音频。</InlineNote>}
        <Field label="目标情绪" required hint="内容保持已实测；情绪变化未客观验证，请试听判断，可换种子多次尝试。">
          <Select
            value={draft.emotion}
            onChange={(e) => onChange((d) => ({ ...d, emotion: e.target.value }))}
          >
            <option value="" disabled>选择目标情绪…</option>
            {EMOTIONS.map((e) => (
              <option key={e} value={e}>{e}</option>
            ))}
          </Select>
        </Field>
        {draft.emotion && (
          <p className="rounded-input border border-line bg-subtle p-3 font-mono text-[11px] leading-[18px] text-ink-3">
            将情感转变为{draft.emotion}。
          </p>
        )}
      </div>
    </Card>
  );
}