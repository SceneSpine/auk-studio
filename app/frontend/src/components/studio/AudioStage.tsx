/**
 * 主音频区（按需显示，紧凑横条）：
 * - 仅 edit / timbre / emotion 渲染；TTS / 音色设计不需要原始音频。
 * - 未上传：细条上传区 + 「最近上传」弹层（不占整屏）。
 * - 已上传：波形一行 + 元信息一行，选区信息内联。
 */
import { useEffect, useRef, useState } from "react";
import { Clock, Lock, RefreshCw, Trash2 } from "lucide-react";
import { api } from "../../api";
import type { AudioMeta, Waveform } from "../../types";
import { fmtDur, fmtTime } from "../../types";
import UploadZone from "../UploadZone";
import WavePlayer, { type Region } from "../WavePlayer";
import type { StudioMode } from "../AppShell";
import { Button, ConfirmDialog, InlineError, StatusBadge, cn, useToast } from "../ui";

interface Props {
  mode: StudioMode;
  audio: AudioMeta | null;
  waveform: Waveform | null;
  region: Region | null;
  onRegionChange: (r: Region | null) => void;
  onAudioLoaded: (a: AudioMeta) => void;
  onReplace: () => void;
  recent: AudioMeta[];
  onRecentChange: (list: AudioMeta[]) => void;
}

function fmt(s: number): string {
  const m = Math.floor(s / 60);
  const ss = (s % 60).toFixed(1).padStart(4, "0");
  return `${m}:${ss}`;
}

export default function AudioStage({
  mode, audio, waveform, region, onRegionChange, onAudioLoaded, onReplace, recent, onRecentChange,
}: Props) {
  const toast = useToast();
  const [recentOpen, setRecentOpen] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<AudioMeta | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState("");
  const recentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!recentOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (recentRef.current && !recentRef.current.contains(e.target as Node)) setRecentOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setRecentOpen(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [recentOpen]);

  /* TTS / 音色设计：无需原始音频 */
  if (mode === "tts" || mode === "design") return null;

  const doDelete = async () => {
    if (!pendingDelete) return;
    setDeleting(true);
    setDeleteError("");
    try {
      await api.audioDelete(pendingDelete.id);
      onRecentChange(recent.filter((a) => a.id !== pendingDelete.id));
      setPendingDelete(null);
      toast("success", "音频记录已删除");
    } catch (e) {
      setDeleteError((e as Error).message);
    } finally {
      setDeleting(false);
    }
  };

  const deleteDialog = (
    <ConfirmDialog
      open={!!pendingDelete}
      onClose={() => setPendingDelete(null)}
      onConfirm={doDelete}
      title="删除音频"
      confirmLabel="删除"
      danger
      loading={deleting}
    >
      <p>删除音频「{pendingDelete?.original_name}」？</p>
      <p className="mt-1 text-xs text-ink-3">有任务或音色引用该音频时会被拒绝；删除不可撤销。</p>
      {deleteError && <div className="mt-2"><InlineError>{deleteError}</InlineError></div>}
    </ConfirmDialog>
  );

  /* 已有主音频：紧凑两行（波形 + 元信息/操作） */
  if (audio) {
    return (
      <section className="shrink-0 rounded-panel border border-line bg-surface px-4 py-3">
        <WavePlayer
          url={api.audioStreamUrl(audio.id)}
          waveform={waveform}
          height={52}
          selectable
          region={region}
          onRegionChange={onRegionChange}
        />
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs text-ink-2">
          <span className="max-w-56 truncate font-medium text-ink" title={audio.original_name}>{audio.original_name}</span>
          <span className="text-ink-3">{fmtDur(audio.duration)} · {audio.sample_rate}Hz · {audio.channels === 1 ? "单声道" : `${audio.channels}声道`}</span>
          <StatusBadge tone="neutral" icon={<Lock size={11} aria-hidden />} className="px-1.5 py-0 text-[10.5px]">只读</StatusBadge>
          {region ? (
            <span className="text-brand">
              选区 {fmt(region.start)} → {fmt(region.end)}（{(region.end - region.start).toFixed(2)}s）
              <button className="ml-1.5 cursor-pointer hover:underline" onClick={() => onRegionChange(null)}>清除</button>
            </span>
          ) : (
            <span className="hidden text-ink-3 md:inline">拖拽波形选择区间 · 原始文件绝不覆盖</span>
          )}
          <Button size="sm" variant="ghost" className="ml-auto h-7 px-2 text-xs" icon={<RefreshCw size={13} />} onClick={onReplace}>
            更换文件
          </Button>
        </div>
        {deleteDialog}
      </section>
    );
  }

  /* 未上传：细条上传区 + 最近上传弹层 */
  return (
    <section className="shrink-0 rounded-panel border border-line bg-surface p-3">
      <div className="flex items-stretch gap-2.5">
        <div className="min-w-0 flex-1">
          <UploadZone compact onUploaded={onAudioLoaded} />
        </div>
        <div className="relative shrink-0" ref={recentRef}>
          <Button
            variant="secondary"
            className="h-full"
            icon={<Clock size={15} />}
            onClick={() => setRecentOpen((o) => !o)}
            aria-expanded={recentOpen}
          >
            最近上传{recent.length > 0 ? ` · ${recent.length}` : ""}
          </Button>
          {recentOpen && (
            <div className="auk-fade-in absolute right-0 top-[calc(100%+6px)] z-30 w-[340px] rounded-panel border border-line bg-surface p-2 shadow-xl">
              {recent.length === 0 ? (
                <p className="px-3 py-6 text-center text-xs text-ink-3">还没有上传记录。上传一段对白开始编辑。</p>
              ) : (
                <div className="max-h-72 space-y-0.5 overflow-y-auto">
                  {recent.slice(0, 12).map((a) => (
                    <div key={a.id} className="flex items-center gap-2 rounded-btn px-2.5 py-2 transition-colors hover:bg-subtle">
                      <button
                        onClick={() => { onAudioLoaded(a); setRecentOpen(false); }}
                        className="flex min-w-0 flex-1 cursor-pointer flex-col text-left"
                        title={`加载 ${a.original_name}`}
                      >
                        <span className="truncate text-[13px] font-medium">{a.original_name}</span>
                        <span className="text-[11px] text-ink-3">{fmtDur(a.duration)} · {a.sample_rate}Hz · {fmtTime(a.created_at)}</span>
                      </button>
                      <button
                        title="删除该音频（有任务引用时会被拒绝）"
                        aria-label={`删除 ${a.original_name}`}
                        className={cn("shrink-0 cursor-pointer p-1 text-ink-3 transition-colors hover:text-err")}
                        onClick={() => { setPendingDelete(a); setDeleteError(""); }}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      {deleteDialog}
    </section>
  );
}