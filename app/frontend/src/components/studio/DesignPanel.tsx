/** 音色设计面板：描述式无参考 TTS（instruct_tts）。 */
import { Sparkles } from "lucide-react";
import { Card, Field, InlineNote, Textarea } from "../ui";
import type { DesignDraft } from "./shared";

interface Props {
  draft: DesignDraft;
  onChange: (v: DesignDraft | ((p: DesignDraft) => DesignDraft)) => void;
}

export default function DesignPanel({ draft, onChange }: Props) {
  return (
    <Card title="音色设计">
      <div className="space-y-4">
        <InlineNote>
          <Sparkles size={13} className="mr-1 inline" aria-hidden />
          描述生成的是「参考音色候选」，不是稳定永久音色：同一描述每次生成可能略有差异。满意的候选可在结果区下载；
          注册到音色库需要关联已上传的音频（见结果区「保存到音色库」按钮说明）。
        </InlineNote>

        <Field label="音色描述" required hint="描述性别、年龄、语气、语速、音色质感等，越具体越稳定。">
          <Textarea
            rows={3}
            value={draft.description}
            onChange={(e) => onChange((d) => ({ ...d, description: e.target.value }))}
            placeholder="例如：一位二十多岁的女性，语气活泼开朗，语速稍快，音色清亮"
          />
        </Field>

        <Field label="试听文案" required hint="用于试听该音色的朗读文本。">
          <Textarea
            rows={3}
            value={draft.text}
            onChange={(e) => onChange((d) => ({ ...d, text: e.target.value }))}
            placeholder="例如：大家好，欢迎来到今天的节目，我们一起聊聊最近发生的新鲜事。"
          />
        </Field>

        <p className="text-xs leading-[18px] text-ink-3">
          无需参考音频。指令模板（实测通过）：
          <span className="break-all font-mono text-[11px]">
            Based on the following description: &quot;{draft.description.trim() || "…"}&quot;, generate speech content &quot;{draft.text.trim() || "…"}&quot;.
          </span>
        </p>
      </div>
    </Card>
  );
}