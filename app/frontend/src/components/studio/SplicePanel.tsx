/** 拼接导出（移植旧 Workspace）：原始波形选区 + 候选起止 + 交叉淡化 → splice；候选选区 → trim。 */
import { useState } from "react";
import { Scissors } from "lucide-react";
import { api } from "../../api";
import type { AudioMeta, FileRef, Waveform } from "../../types";
import { fmtDur } from "../../types";
import WavePlayer, { type Region } from "../WavePlayer";
import { Button, DownloadLink, Field, InlineError, Input, InlineNote } from "../ui";

interface Props {
  jobId: string;
  candidate: FileRef;
  audio: AudioMeta;
  waveform: Waveform | null;
  /** 原始波形替换区间（与主音频区选区联动） */
  region: Region | null;
  onRegionChange: (r: Region | null) => void;
  defaultCrossfadeMs: string;
}

interface Exported {
  file_id: string;
  url: string;
  duration: number;
}

export default function SplicePanel({ jobId, candidate, audio, waveform, region, onRegionChange, defaultCrossfadeMs }: Props) {
  const [candRegion, setCandRegion] = useState<Region | null>(null);
  const [crossfadeMs, setCrossfadeMs] = useState(defaultCrossfadeMs || "30");
  const [busy, setBusy] = useState<"splice" | "trim" | null>(null);
  const [error, setError] = useState("");
  const [spliced, setSpliced] = useState<Exported | null>(null);
  const [segment, setSegment] = useState<Exported | null>(null);

  const doSplice = async () => {
    if (!region) return;
    setBusy("splice");
    setError("");
    try {
      const r = await api.splice(jobId, {
        start_s: region.start,
        end_s: region.end,
        cand_start_s: candRegion?.start ?? 0,
        cand_end_s: candRegion?.end ?? null,
        crossfade_ms: Number(crossfadeMs) || 0,
      });
      setSpliced(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const doTrim = async () => {
    if (!candRegion) return;
    setBusy("trim");
    setError("");
    try {
      const r = await api.trim(jobId, { start_s: candRegion.start, end_s: candRegion.end });
      setSegment(r);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-4 rounded-input border border-line p-4">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Scissors size={15} aria-hidden /> 拼接导出（保留未修改区域的原始 PCM）
      </div>
      <InlineNote>
        候选是模型对整段音频的重生成，修改范围之外的波形不保证与原始完全一致。拼接把候选选区插回原始音频，未修改区域保留原始声音；原文件绝不覆盖。
      </InlineNote>

      <div>
        <div className="mb-1 text-xs font-medium text-ink-2">① 在原始波形上拖选要被替换的区间（与上方主选区联动）</div>
        <WavePlayer
          url={api.audioStreamUrl(audio.id)}
          waveform={waveform}
          height={64}
          selectable
          region={region}
          onRegionChange={onRegionChange}
        />
      </div>
      <div>
        <div className="mb-1 text-xs font-medium text-ink-2">②（可选）在候选波形上拖选用于插入的部分；不选则使用整段候选</div>
        <WavePlayer
          url={api.fileUrl(candidate.id)}
          height={64}
          selectable
          region={candRegion}
          onRegionChange={setCandRegion}
        />
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <Field label="边界交叉淡化（毫秒）">
          <Input
            className="w-28"
            value={crossfadeMs}
            onChange={(e) => setCrossfadeMs(e.target.value.replace(/[^0-9]/g, ""))}
            inputMode="numeric"
          />
        </Field>
        <Button variant="primary" disabled={!region || busy !== null} loading={busy === "splice"} onClick={doSplice}>
          拼回完整音频
        </Button>
        <Button disabled={!candRegion || busy !== null} loading={busy === "trim"} onClick={doTrim}>
          导出候选选区片段
        </Button>
      </div>

      {error && <InlineError>{error}</InlineError>}

      {spliced && (
        <div className="rounded-input border border-line bg-subtle p-3">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs font-medium text-ink-2">拼接结果（{fmtDur(spliced.duration)} · 未修改区域来自原始音频）</span>
            <DownloadLink href={api.fileUrl(spliced.file_id, true)}>下载完整 WAV</DownloadLink>
          </div>
          <WavePlayer url={api.fileUrl(spliced.file_id)} height={56} />
        </div>
      )}
      {segment && (
        <div className="rounded-input border border-line bg-subtle p-3">
          <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
            <span className="text-xs font-medium text-ink-2">修改片段（{fmtDur(segment.duration)}）</span>
            <DownloadLink href={api.fileUrl(segment.file_id, true)}>下载片段 WAV</DownloadLink>
          </div>
          <WavePlayer url={api.fileUrl(segment.file_id)} height={56} />
        </div>
      )}
    </div>
  );
}