import { useRef, useState } from "react";
import { UploadCloud } from "lucide-react";
import { api } from "../api";
import type { AudioMeta } from "../types";
import { fmtBytes, fmtDur } from "../types";
import { cn, InlineError, Progress, Spinner } from "./ui";

interface Props {
  onUploaded: (a: AudioMeta) => void;
  compact?: boolean;
}

export default function UploadZone({ onUploaded, compact = false }: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const lastFileRef = useRef<File | null>(null);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pct, setPct] = useState(0);
  const [error, setError] = useState("");

  const doUpload = async (file: File) => {
    lastFileRef.current = file;
    setBusy(true);
    setError("");
    setPct(0);
    try {
      const meta = await api.uploadAudio(file, setPct);
      onUploaded(meta);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <div
        onClick={() => !busy && inputRef.current?.click()}
        onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault();
          setDrag(false);
          const f = e.dataTransfer.files?.[0];
          if (f && !busy) void doUpload(f);
        }}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if ((e.key === "Enter" || e.key === " ") && !busy) {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        aria-label="上传音频：拖拽文件到此处，或按回车选择文件"
        className={cn(
          "cursor-pointer rounded-panel border-2 border-dashed text-center transition-colors",
          drag ? "border-brand bg-brand-tint" : "border-line bg-subtle hover:border-brand/50",
          compact ? "px-4 py-2.5" : "py-10",
        )}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".wav,.mp3,.m4a,.flac,.ogg,.aac,.aiff,.aif,.mp4,audio/*"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void doUpload(f);
            e.target.value = "";
          }}
        />
        {busy ? (
          compact ? (
            <div className="flex items-center justify-center gap-2 text-[13px] text-ink-2">
              <Spinner size={15} /> 上传中 {pct}%
              <span className="w-28"><Progress value={pct} label="上传进度" /></span>
            </div>
          ) : (
            <div className="mx-auto max-w-sm space-y-2 px-4">
              <div className="flex items-center justify-center gap-2 text-sm text-ink-2">
                <Spinner /> 上传中 {pct}%（随后自动解码与生成波形）
              </div>
              <Progress value={pct} label="上传进度" />
            </div>
          )
        ) : compact ? (
          <div className="flex flex-wrap items-center justify-center gap-x-2 gap-y-0.5">
            <UploadCloud size={16} className="text-ink-3" aria-hidden />
            <span className="text-[13px] font-medium text-ink-2">拖拽或点击上传音频</span>
            <span className="hidden text-xs text-ink-3 sm:inline">WAV / MP3 / M4A / FLAC · 只读保留 · 仅本机</span>
          </div>
        ) : (
          <>
            <UploadCloud size={24} className="mx-auto mb-2 text-ink-3" aria-hidden />
            <div className="text-sm font-medium text-ink-2">拖拽音频到此处，或点击选择文件</div>
            <div className="mt-1 text-xs text-ink-3">WAV / MP3 / M4A / FLAC 等 · 原始文件只读保留 · 仅本机处理</div>
          </>
        )}
      </div>
      {error && (
        <div className="mt-2">
          <InlineError onRetry={lastFileRef.current ? () => void doUpload(lastFileRef.current!) : undefined}>
            {error}
          </InlineError>
        </div>
      )}
    </div>
  );
}

export function AudioInfoBar({ a }: { a: AudioMeta }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2">
      <span className="max-w-64 truncate font-medium text-ink" title={a.original_name}>{a.original_name}</span>
      <span>{fmtDur(a.duration)}</span>
      <span>{a.sample_rate} Hz</span>
      <span>{a.channels === 1 ? "单声道" : `${a.channels} 声道`}</span>
      {a.bit_depth ? <span>{a.bit_depth}-bit</span> : null}
      <span>{fmtBytes(a.size_bytes)}</span>
    </div>
  );
}