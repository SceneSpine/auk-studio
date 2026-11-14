/**
 * 新建音色弹窗：名称/描述/标签 + 参考音频（上传或从已有音频选择）+
 * 强制授权确认（未勾选禁用提交）+ 允许用途。
 */
import { useEffect, useRef, useState } from "react";
import { FileAudio, Upload, X } from "lucide-react";
import { api } from "../../api";
import type { AudioMeta } from "../../types";
import { fmtDur } from "../../types";
import {
  Button,
  Checkbox,
  Dialog,
  Field,
  InlineError,
  InlineNote,
  Input,
  Progress,
  Select,
  Tabs,
  Textarea,
  useToast,
} from "../ui";
import { CONSENT_STATEMENT, parseTags } from "./shared";

export default function CreateVoiceDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const toast = useToast();
  const fileRef = useRef<HTMLInputElement>(null);

  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [tagsInput, setTagsInput] = useState("");
  const [audioMode, setAudioMode] = useState("upload");
  const [audio, setAudio] = useState<AudioMeta | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadPct, setUploadPct] = useState(0);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [audioList, setAudioList] = useState<AudioMeta[] | null>(null);
  const [audioListError, setAudioListError] = useState<string | null>(null);
  const [consent, setConsent] = useState(false);
  const [allowedUse, setAllowedUse] = useState("personal_research");
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [nameTouched, setNameTouched] = useState(false);

  /* 打开时重置表单 */
  useEffect(() => {
    if (!open) return;
    setName("");
    setDesc("");
    setTagsInput("");
    setAudioMode("upload");
    setAudio(null);
    setUploading(false);
    setUploadPct(0);
    setUploadError(null);
    setConsent(false);
    setAllowedUse("personal_research");
    setBusy(false);
    setSubmitError(null);
    setNameTouched(false);
  }, [open]);

  /* 已有音频列表（选择器用） */
  useEffect(() => {
    if (!open) return;
    let alive = true;
    setAudioListError(null);
    api
      .audioList()
      .then((list) => alive && setAudioList(list))
      .catch((e) => alive && setAudioListError((e as Error).message));
    return () => {
      alive = false;
    };
  }, [open]);

  const tags = parseTags(tagsInput);
  const nameError = nameTouched && !name.trim() ? "请输入音色名称" : null;
  const canSubmit = !!name.trim() && !!audio && consent && !busy && !uploading;

  const onFile = async (file: File | undefined) => {
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    setUploadPct(0);
    try {
      const meta = await api.uploadAudio(file, setUploadPct);
      setAudio(meta);
      toast("success", `参考音频已上传：${meta.original_name}`);
    } catch (e) {
      setUploadError((e as Error).message);
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = "";
    }
  };

  const submit = async () => {
    if (!canSubmit || !audio) return;
    setBusy(true);
    setSubmitError(null);
    try {
      const v = await api.createVoice({
        name: name.trim(),
        description: desc.trim(),
        tags,
        audio_id: audio.id,
        consent_confirmed: true,
        allowed_use: allowedUse,
        source: "upload",
      });
      toast("success", `已创建音色「${v.name}」`);
      onCreated();
      onClose();
    } catch (e) {
      setSubmitError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="新建音色"
      width="max-w-xl"
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant="primary" loading={busy} disabled={!canSubmit} onClick={submit}>
            创建音色
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <InlineNote>
          保存的是「参考音色」（零样本克隆的参考样本），不是永久训练音色。参考音频仅保存在本机，不会上传到任何服务器。
        </InlineNote>

        <Field label="名称" required error={nameError}>
          <Input
            value={name}
            onChange={(e) => setName(e.target.value)}
            onBlur={() => setNameTouched(true)}
            placeholder="例如：旁白 · 沉稳男声"
            maxLength={60}
          />
        </Field>

        <Field label="描述" hint="可选：音色特点、适用场景">
          <Textarea value={desc} onChange={(e) => setDesc(e.target.value)} placeholder="低沉、平稳，适合纪录片旁白" maxLength={300} />
        </Field>

        <Field label="标签" hint="用逗号分隔，例如：旁白,男声,沉稳">
          <Input value={tagsInput} onChange={(e) => setTagsInput(e.target.value)} placeholder="旁白,男声,沉稳" />
        </Field>
        {tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {tags.map((t) => (
              <span key={t} className="rounded-full bg-brand-tint px-2 py-0.5 text-[11px] leading-4 text-brand">
                {t}
              </span>
            ))}
          </div>
        )}

        {/* 参考音频 */}
        <div>
          <div className="mb-1.5 flex items-center gap-1 text-[13px] font-medium">
            参考音频<span className="text-err" aria-hidden>*</span>
          </div>
          <Tabs
            items={[
              { key: "upload", label: "上传新音频" },
              { key: "existing", label: "从已有音频选择" },
            ]}
            value={audioMode}
            onChange={(k) => setAudioMode(k)}
            className="mb-3"
          />

          {audioMode === "upload" ? (
            <div className="space-y-2">
              <input
                ref={fileRef}
                type="file"
                accept="audio/*,.wav,.mp3,.m4a,.flac,.aac,.ogg"
                className="hidden"
                onChange={(e) => onFile(e.target.files?.[0])}
              />
              <Button icon={<Upload size={15} aria-hidden />} loading={uploading} onClick={() => fileRef.current?.click()}>
                {uploading ? `上传中 ${uploadPct}%` : "选择音频文件"}
              </Button>
              {uploading && <Progress value={uploadPct} label="上传进度" />}
              {uploadError && <InlineError onRetry={() => fileRef.current?.click()}>上传失败：{uploadError}</InlineError>}
            </div>
          ) : audioListError ? (
            <InlineError
              onRetry={() => {
                setAudioListError(null);
                api
                  .audioList()
                  .then(setAudioList)
                  .catch((e) => setAudioListError((e as Error).message));
              }}
            >
              加载音频列表失败：{audioListError}
            </InlineError>
          ) : audioList === null ? (
            <p className="text-[13px] text-ink-3">加载音频列表…</p>
          ) : audioList.length === 0 ? (
            <p className="text-[13px] text-ink-3">还没有已上传的音频，请切换到「上传新音频」。</p>
          ) : (
            <Select
              value={audio?.id ?? ""}
              onChange={(e) => setAudio(audioList.find((a) => a.id === e.target.value) ?? null)}
              aria-label="选择已有音频"
            >
              <option value="">请选择音频…</option>
              {audioList.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.original_name} · {fmtDur(a.duration)}
                </option>
              ))}
            </Select>
          )}

          {/* 已选参考音频 */}
          {audio && (
            <div className="mt-2 flex items-center gap-2 rounded-input border border-line bg-subtle px-3 py-2">
              <FileAudio size={15} className="shrink-0 text-brand" aria-hidden />
              <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{audio.original_name}</span>
              <span className="shrink-0 text-xs text-ink-3">{fmtDur(audio.duration)}</span>
              <button
                className="shrink-0 cursor-pointer text-ink-3 hover:text-ink"
                aria-label="移除已选音频"
                onClick={() => setAudio(null)}
              >
                <X size={14} />
              </button>
            </div>
          )}
        </div>

        {/* 允许用途 */}
        <Field label="允许用途">
          <Select value={allowedUse} onChange={(e) => setAllowedUse(e.target.value)}>
            <option value="personal_research">个人研究</option>
            <option value="evaluation">评估</option>
            <option value="non_commercial">非商业创作</option>
          </Select>
        </Field>

        {/* 强制授权确认 */}
        <div className="rounded-input border border-warn/40 bg-warn-tint/50 p-3.5">
          <Checkbox checked={consent} onChange={setConsent} label={<span className="text-[13px] leading-5">{CONSENT_STATEMENT}</span>} />
          {!consent && <p className="mt-2 text-xs leading-[18px] text-warn">勾选确认后才能创建音色。克隆真实人物声音前，请确保已取得相应授权。</p>}
        </div>

        {submitError && <InlineError>创建失败：{submitError}</InlineError>}
      </div>
    </Dialog>
  );
}