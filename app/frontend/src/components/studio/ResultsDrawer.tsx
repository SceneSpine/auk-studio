/** 结果抽屉：候选版本卡（多次生成不覆盖）+ A/B + 接受/评分/最佳 + 重做 + 拼接/片段导出。 */
import { useEffect, useState } from "react";
import { ChevronDown, ListMusic, RefreshCw, Star, ThumbsDown, ThumbsUp } from "lucide-react";
import { api } from "../../api";
import type { AudioMeta, FileRef, Job, Waveform } from "../../types";
import { MODE_LABEL, fmtAgo, fmtDur } from "../../types";
import ABPlayer from "../ABPlayer";
import WavePlayer, { type Region } from "../WavePlayer";
import type { StudioMode, ViewKey } from "../AppShell";
import {
  Button, CopyButton, DownloadLink, EmptyState, InlineError, Skeleton, StatusBadge, Tooltip, cn, useToast,
} from "../ui";
import SaveVoiceDialog from "./SaveVoiceDialog";
import SplicePanel from "./SplicePanel";
import { jobParamsSummary } from "./shared";

interface Entry {
  job: Job;
  file: FileRef;
}

interface Props {
  open: boolean;
  onToggle: () => void;
  audio: AudioMeta | null;
  waveform: Waveform | null;
  current: { job: Job; files: FileRef[] } | null;
  historyJobs: Job[];
  mainRegion: Region | null;
  onMainRegionChange: (r: Region | null) => void;
  crossfadeMs: string;
  busy: boolean;
  onRedo: (job: Job) => void;
  onNavigate: (v: ViewKey, m?: StudioMode) => void;
  /** 底部停靠模式：头部常驻 + 内容内部滚动，不需要整页下拉 */
  docked?: boolean;
}

export default function ResultsDrawer({
  open, onToggle, audio, waveform, current, historyJobs, mainRegion, onMainRegionChange,
  crossfadeMs, busy, onRedo, onNavigate, docked = false,
}: Props) {
  const toast = useToast();
  const [entries, setEntries] = useState<Entry[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [saveTarget, setSaveTarget] = useState<Entry | null>(null);

  /* 当前结果 + 同上下文历史 completed 任务（新候选不覆盖旧候选） */
  useEffect(() => {
    let alive = true;
    (async () => {
      const list: Entry[] = [];
      const seen = new Set<string>();
      if (current) {
        const f = current.files.find((x) => x.kind === "candidate" && x.exists !== false);
        if (f) {
          list.push({ job: current.job, file: f });
          seen.add(current.job.id);
        }
      }
      const others = historyJobs.filter((j) => !seen.has(j.id)).slice(0, 9);
      if (others.length > 0) setLoadingHistory(true);
      const results = await Promise.allSettled(others.map((j) => api.jobResult(j.id)));
      if (!alive) return;
      let failed = 0;
      for (const r of results) {
        if (r.status === "fulfilled") {
          const f = r.value.files.find((x) => x.kind === "candidate" && x.exists !== false);
          if (f && !seen.has(r.value.job.id)) {
            list.push({ job: r.value.job, file: f });
            seen.add(r.value.job.id);
          }
        } else {
          failed += 1;
        }
      }
      list.sort((a, b) => b.file.created_at - a.file.created_at);
      setEntries(list);
      setSelectedId((prev) => (prev && list.some((e) => e.file.id === prev) ? prev : list[0]?.file.id ?? null));
      setLoadingHistory(false);
      setHistoryError(failed > 0 ? `${failed} 条历史结果加载失败（可能已被清理）` : "");
    })();
    return () => { alive = false; };
  }, [current, historyJobs]);

  const selected = entries.find((e) => e.file.id === selectedId) ?? null;

  const patchFile = (id: string, patch: Partial<FileRef>) =>
    setEntries((es) => es.map((e) => (e.file.id === id ? { ...e, file: { ...e.file, ...patch } } : e)));
  const patchJob = (id: string, patch: Partial<Job>) =>
    setEntries((es) => es.map((e) => (e.job.id === id ? { ...e, job: { ...e.job, ...patch } } : e)));

  const rate = async (file: FileRef, rating: number | null) => {
    try {
      const updated = await api.rateOutput(file.id, { rating });
      patchFile(file.id, updated);
    } catch (e) {
      toast("error", `评分失败：${(e as Error).message}`);
    }
  };
  const toggleFavorite = async (file: FileRef) => {
    try {
      const updated = await api.rateOutput(file.id, { favorite: !file.favorite });
      patchFile(file.id, updated);
      toast("success", updated.favorite ? "已标记为最佳候选" : "已取消最佳标记");
    } catch (e) {
      toast("error", `标记失败：${(e as Error).message}`);
    }
  };
  const accept = async (job: Job, next: boolean | null) => {
    try {
      await api.acceptJob(job.id, next);
      patchJob(job.id, { accepted: next == null ? null : next ? 1 : 0 });
    } catch (e) {
      toast("error", `操作失败：${(e as Error).message}`);
    }
  };

  const canSplice = !!audio && !!selected && selected.job.audio_id === audio.id;

  return (
    <section className={cn("rounded-panel border border-line bg-surface", docked && "flex min-h-0 shrink-0 flex-col")}>
      <button
        className={cn("flex w-full cursor-pointer items-center justify-between gap-3 px-5 text-left", docked ? "py-2.5" : "py-3.5")}
        onClick={onToggle}
        aria-expanded={open}
      >
        <span className="flex items-center gap-2 text-[15px] font-semibold">
          <ListMusic size={17} aria-hidden />
          生成结果
          {entries.length > 0 && <StatusBadge tone="neutral">{entries.length} 个候选</StatusBadge>}
          {busy && <StatusBadge tone="progress">生成中</StatusBadge>}
        </span>
        <span className="flex items-center gap-2">
          {docked && !open && entries.length > 0 && (
            <span className="hidden text-xs font-normal text-ink-3 sm:inline">点击展开试听 / A-B / 导出</span>
          )}
          <ChevronDown size={16} className={cn("text-ink-3 transition-transform", open && "rotate-180")} aria-hidden />
        </span>
      </button>

      {open && (
        <div className={cn("border-t border-line", docked ? "min-h-0 space-y-3 overflow-y-auto p-4 lg:max-h-[36vh]" : "space-y-4 p-5")}>
          {historyError && <InlineError>{historyError}</InlineError>}

          {entries.length === 0 && !loadingHistory && busy && (
            <div className="flex items-center gap-2.5 rounded-input bg-subtle px-4 py-3 text-[13px] text-ink-2">
              <RefreshCw size={15} className="animate-spin text-brand" aria-hidden />
              任务运行中，完成后候选会自动出现在这里（阶段进度见右侧生成配置）。
            </div>
          )}
          {entries.length === 0 && !loadingHistory && !busy && (
            <EmptyState
              icon={<ListMusic size={24} />}
              title="还没有生成结果"
              description="点击「生成候选音频」后，候选会出现在这里；同一音频的历史候选也会一并列出，不会被新结果覆盖。"
              className={docked ? "py-5" : "py-8"}
            />
          )}
          {loadingHistory && entries.length === 0 && <Skeleton className="h-32" />}

          {/* 候选版本卡列表 */}
          <div className="space-y-3">
            {entries.map((e, idx) => {
              const isSel = e.file.id === selectedId;
              const params = jobParamsSummary(e.job, audio?.original_name);
              return (
                <div
                  key={e.file.id}
                  className={cn(
                    "rounded-panel border transition-colors",
                    docked ? "space-y-2.5 p-3" : "space-y-3 p-4",
                    isSel ? "border-brand/50 bg-brand-tint/40" : "border-line",
                  )}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <button
                      className="flex cursor-pointer items-center gap-2 text-left"
                      onClick={() => setSelectedId(e.file.id)}
                      aria-pressed={isSel}
                      title="设为对比/导出目标"
                    >
                      <span
                        className={cn(
                          "flex h-4 w-4 items-center justify-center rounded-full border",
                          isSel ? "border-brand bg-brand" : "border-line",
                        )}
                        aria-hidden
                      >
                        {isSel && <span className="h-1.5 w-1.5 rounded-full bg-white" />}
                      </span>
                      <span className="text-sm font-semibold">候选 {entries.length - idx}</span>
                    </button>
                    <StatusBadge tone="neutral">{MODE_LABEL[e.job.mode] ?? e.job.mode}</StatusBadge>
                    {!!e.file.favorite && <StatusBadge tone="warn" icon={<Star size={12} fill="currentColor" aria-hidden />}>最佳</StatusBadge>}
                    {e.job.accepted === 1 && <StatusBadge tone="ready">已接受</StatusBadge>}
                    {e.job.accepted === 0 && <StatusBadge tone="error">未接受</StatusBadge>}
                    <span className="ml-auto text-xs text-ink-3">{fmtAgo(e.file.created_at)}</span>
                  </div>

                  <WavePlayer url={api.fileUrl(e.file.id)} height={docked ? 48 : 56} />

                  <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-3">
                    <span>{fmtDur(e.file.duration ?? e.job.output_duration)}</span>
                    <span>{e.job.model_variant === "base" ? "AuK Base" : "AuK-Flash"}</span>
                    <span>{e.job.bits ? `${e.job.bits}-bit` : "fp32"}</span>
                    {e.job.seed != null && <span>seed {e.job.seed}</span>}
                    {e.job.nfe != null && <span>NFE {e.job.nfe}</span>}
                    <span>RTF {e.job.rtf ?? "—"}</span>
                    <span>耗时 {fmtDur(e.job.elapsed_s)}</span>
                  </div>

                  <div className="flex flex-wrap items-center gap-1.5">
                    <DownloadLink href={api.fileUrl(e.file.id, true)} />
                    <CopyButton text={params} label="复制参数" />
                    <Button
                      size="sm"
                      variant={e.file.favorite ? "primary" : "ghost"}
                      icon={<Star size={14} fill={e.file.favorite ? "currentColor" : "none"} />}
                      onClick={() => toggleFavorite(e.file)}
                    >
                      {e.file.favorite ? "已标记最佳" : "标记最佳"}
                    </Button>
                    <Button size="sm" variant="ghost" icon={<RefreshCw size={14} />} disabled={busy} onClick={() => onRedo(e.job)}>
                      重做
                    </Button>
                    {e.file.audio_id ? (
                      <Button size="sm" variant="ghost" onClick={() => setSaveTarget(e)}>保存到音色库</Button>
                    ) : (
                      <Tooltip label="该候选无关联的已注册音频（描述式生成无输入音频），无法写入音色库；请先下载候选">
                        <span>
                          <Button size="sm" variant="ghost" disabled>保存到音色库</Button>
                        </span>
                      </Tooltip>
                    )}

                    {/* 评分 1–5 星 */}
                    <span className="ml-1 inline-flex items-center gap-0.5" role="radiogroup" aria-label="质量评分">
                      {[1, 2, 3, 4, 5].map((n) => (
                        <button
                          key={n}
                          role="radio"
                          aria-checked={e.file.rating === n}
                          aria-label={`${n} 星`}
                          title={`${n} 星${e.file.rating === n ? "（点击清除）" : ""}`}
                          className="cursor-pointer p-0.5"
                          onClick={() => rate(e.file, e.file.rating === n ? null : n)}
                        >
                          <Star
                            size={15}
                            className={n <= (e.file.rating ?? 0) ? "fill-warn text-warn" : "text-ink-3 hover:text-warn"}
                          />
                        </button>
                      ))}
                    </span>

                    {/* 接受标记 */}
                    <span className="ml-auto inline-flex items-center gap-1">
                      <span className="text-xs text-ink-3">接受：</span>
                      <Button
                        size="sm"
                        variant={e.job.accepted === 1 ? "primary" : "ghost"}
                        icon={<ThumbsUp size={14} />}
                        onClick={() => accept(e.job, e.job.accepted === 1 ? null : true)}
                        aria-label="接受该结果"
                      >
                        接受
                      </Button>
                      <Button
                        size="sm"
                        variant={e.job.accepted === 0 ? "danger" : "ghost"}
                        icon={<ThumbsDown size={14} />}
                        onClick={() => accept(e.job, e.job.accepted === 0 ? null : false)}
                        aria-label="不接受该结果"
                      >
                        不接受
                      </Button>
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* A/B 对比 */}
          {audio && selected && (
            <div className="space-y-2 rounded-input border border-line p-4">
              <div className="text-sm font-semibold">A/B 对比 · 原始 vs 候选 {entries.findIndex((e) => e.file.id === selectedId) >= 0 ? entries.length - entries.findIndex((e) => e.file.id === selectedId) : ""}</div>
              <ABPlayer
                urlA={api.audioStreamUrl(audio.id)}
                urlB={api.fileUrl(selected.file.id)}
                waveformA={waveform}
                labelA={`原始 · ${audio.original_name}`}
                labelB={`生成候选 · ${fmtDur(selected.file.duration ?? selected.job.output_duration)} · ${selected.job.bits ? selected.job.bits + "-bit" : "fp32"}${selected.job.seed != null ? ` · seed ${selected.job.seed}` : ""}`}
              />
            </div>
          )}

          {/* 拼接 / 片段导出 */}
          {canSplice && selected && audio && (
            <SplicePanel
              key={`${selected.job.id}:${selected.file.id}`}
              jobId={selected.job.id}
              candidate={selected.file}
              audio={audio}
              waveform={waveform}
              region={mainRegion}
              onRegionChange={onMainRegionChange}
              defaultCrossfadeMs={crossfadeMs}
            />
          )}
          {audio && selected && !canSplice && (
            <p className="text-xs text-ink-3">该候选来自其他源音频（或无源音频），不能与当前主音频拼接；切换到对应源音频后可用拼接导出。</p>
          )}

          <p className="text-xs leading-[18px] text-ink-3">
            原文件绝不覆盖：候选、拼接与片段导出均为新文件，只读保存在本机数据目录。
            <button className="ml-1 cursor-pointer text-brand hover:underline" onClick={() => onNavigate("jobs")}>查看全部任务历史</button>
          </p>
        </div>
      )}

      <SaveVoiceDialog
        open={!!saveTarget}
        onClose={() => setSaveTarget(null)}
        file={saveTarget?.file ?? null}
        job={saveTarget?.job ?? null}
        onSaved={() => {}}
      />
    </section>
  );
}