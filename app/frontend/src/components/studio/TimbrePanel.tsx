/** 音色重塑面板：源音频 + 目标音色描述（timbre）。 */
import { Card, Field, InlineNote, Textarea } from "../ui";
import type { TimbreDraft } from "./shared";

interface Props {
  draft: TimbreDraft;
  onChange: (v: TimbreDraft | ((p: TimbreDraft) => TimbreDraft)) => void;
  hasAudio: boolean;
}

export default function TimbrePanel({ draft, onChange, hasAudio }: Props) {
  return (
    <Card title="音色重塑">
      <div className="space-y-4">
        {!hasAudio && <InlineNote tone="warn">请先在上方上传源音频：音色重塑在源音频上修改音色，内容逐字保持。</InlineNote>}
        <InlineNote>
          实测结论：内容保持已验证（中文模板逐字保持）；音色变化本身是主观维度，请在结果区试听确认，必要时换种子多生成几个候选。
        </InlineNote>
        <Field label="目标音色描述" required hint="描述想要的声音特质，源音频的台词内容保持不变。">
          <Textarea
            rows={3}
            value={draft.description}
            onChange={(e) => onChange((d) => ({ ...d, description: e.target.value }))}
            placeholder="例如：低沉沙哑的中年男性，语速沉稳，带有磁性"
          />
        </Field>
        {draft.description.trim() && (
          <p className="break-all rounded-input border border-line bg-subtle p-3 font-mono text-[11px] leading-[18px] text-ink-3">
            请将这段音频的音色修改为符合以下描述的声音：“{draft.description.trim()}”。
          </p>
        )}
      </div>
    </Card>
  );
}