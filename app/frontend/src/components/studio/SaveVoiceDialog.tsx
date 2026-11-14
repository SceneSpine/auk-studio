/** 保存候选到音色库：名称/描述/标签 + 授权确认（强制）。按契约 audio_id 必须存在。 */
import { useEffect, useState } from "react";
import { api } from "../../api";
import type { FileRef, Job, Voice } from "../../types";
import { Button, Checkbox, Dialog, Field, InlineError, Input, Textarea, useToast } from "../ui";

interface Props {
  open: boolean;
  onClose: () => void;
  file: FileRef | null;
  job: Job | null;
  onSaved: (v: Voice) => void;
}

const CONSENT_STATEMENT = "我确认对该参考声音拥有合法使用权，仅在本机用于非商业研究/评估用途";

export default function SaveVoiceDialog({ open, onClose, file, job, onSaved }: Props) {
  const toast = useToast();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (open) {
      setName("");
      setDescription(job?.description || "");
      setTags("");
      setConsent(false);
      setError("");
    }
  }, [open, job?.description]);

  const save = async () => {
    if (!file?.audio_id || !name.trim() || !consent) return;
    setBusy(true);
    setError("");
    try {
      const v = await api.createVoice({
        name: name.trim(),
        description: description.trim(),
        tags: tags.split(/[,，]/).map((t) => t.trim()).filter(Boolean),
        audio_id: file.audio_id,
        consent_confirmed: true,
        allowed_use: "非商业研究/评估",
        source: "generated",
        job_id: job?.id ?? null,
      });
      toast("success", `已保存参考音色「${v.name}」到音色库`);
      onSaved(v);
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="保存到音色库"
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" loading={busy} disabled={!name.trim() || !consent} onClick={save}>
            保存参考音色
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <p className="text-xs leading-[18px] text-ink-3">
          保存的是「参考音色」（参考音频 + 授权记录），不是永久训练音色。将关联该候选对应的源音频。
        </p>
        <Field label="名称" required>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="例如：清亮女声 · 活泼" maxLength={40} />
        </Field>
        <Field label="描述">
          <Textarea rows={2} value={description} onChange={(e) => setDescription(e.target.value)} placeholder="音色特征备注" />
        </Field>
        <Field label="标签" hint="用逗号分隔，例如：女声, 活泼, 旁白">
          <Input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="可选" />
        </Field>
        <div className="rounded-input border border-line bg-subtle p-3">
          <Checkbox checked={consent} onChange={setConsent} label={<span className="text-xs leading-[18px]">{CONSENT_STATEMENT}。</span>} />
        </div>
        {error && <InlineError>{error}</InlineError>}
      </div>
    </Dialog>
  );
}