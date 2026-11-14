import { useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/dist/plugins/regions.esm.js";
import { Pause, Play } from "lucide-react";
import type { Waveform } from "../types";
import {
  claimActive,
  claimActiveIfNone,
  onPauseOthers,
  pauseOthers,
  releaseActive,
  type PlayerHandle,
} from "./studio/playback";

export interface Region {
  start: number;
  end: number;
}

interface Props {
  url: string;
  waveform?: Waveform | null;
  height?: number;
  color?: string;
  progressColor?: string;
  /** 启用区域拖选（用于拼接区间/片段裁剪） */
  selectable?: boolean;
  region?: Region | null;
  onRegionChange?: (r: Region | null) => void;
  onReady?: (duration: number) => void;
  compact?: boolean;
  label?: string;
}

function fmt(s: number): string {
  const m = Math.floor(s / 60);
  const ss = (s % 60).toFixed(1).padStart(4, "0");
  return `${m}:${ss}`;
}

const REGION_COLOR = "rgba(83, 116, 245, 0.18)";

export default function WavePlayer({
  url, waveform, height = 72, color, progressColor,
  selectable = false, region, onRegionChange, onReady, compact = false, label,
}: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const wsRef = useRef<WaveSurfer | null>(null);
  const regionsRef = useRef<RegionsPlugin | null>(null);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(waveform?.duration ?? 0);
  const [ready, setReady] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const cbRef = useRef({ onRegionChange, onReady });
  cbRef.current = { onRegionChange, onReady };

  /* 播放互斥 + Space 活动播放器注册（实例级 token，不随渲染重建） */
  const selfToken = useRef<object>({});
  const handleRef = useRef<PlayerHandle>({
    toggle: () => {
      const ws = wsRef.current;
      if (!ws) return;
      if (ws.isPlaying()) ws.pause();
      else void ws.play().catch(() => {});
    },
    pause: () => wsRef.current?.pause(),
  });
  useEffect(() => {
    claimActiveIfNone(handleRef.current);
    const off = onPauseOthers((src) => {
      if (src !== selfToken.current) wsRef.current?.pause();
    });
    return () => {
      off();
      releaseActive(handleRef.current);
    };
  }, []);

  /* WaveSurfer 实例仅在 url / 波形数据变化时重建，不随普通 state 重建 */
  useEffect(() => {
    if (!containerRef.current) return;
    const isDark = document.documentElement.classList.contains("dark");
    const ws = WaveSurfer.create({
      container: containerRef.current,
      url,
      height,
      waveColor: color ?? (isDark ? "#3d4450" : "#c9d2de"),
      progressColor: progressColor ?? (isDark ? "#7792ff" : "#5374f5"),
      cursorColor: isDark ? "#a4b0c1" : "#66758b",
      cursorWidth: 1,
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      normalize: true,
      interact: true,
      peaks: waveform ? [waveform.points.flatMap(([mn, mx]) => [mx, mn])] : undefined,
      duration: waveform?.duration,
    });
    wsRef.current = ws;
    setReady(false);
    setTime(0);
    setDuration(waveform?.duration ?? 0);
    setLoadError(false);

    if (selectable) {
      const regions = ws.registerPlugin(RegionsPlugin.create());
      regionsRef.current = regions;
      regions.enableDragSelection({ color: REGION_COLOR });
      regions.on("region-created", (r) => {
        // 只保留一个区域
        regions.getRegions().forEach((other) => {
          if (other.id !== r.id) other.remove();
        });
        cbRef.current.onRegionChange?.({ start: r.start, end: r.end });
      });
      regions.on("region-updated", (r) => {
        cbRef.current.onRegionChange?.({ start: r.start, end: r.end });
      });
    }

    ws.on("ready", (d) => {
      setDuration(d);
      setReady(true);
      cbRef.current.onReady?.(d);
    });
    ws.on("play", () => {
      setPlaying(true);
      claimActive(handleRef.current);
      pauseOthers(selfToken.current);
    });
    ws.on("pause", () => setPlaying(false));
    ws.on("finish", () => setPlaying(false));
    ws.on("timeupdate", (t) => setTime(t));
    ws.on("error", () => setLoadError(true));

    /* 主题切换时为已存在实例重新着色（不重建实例） */
    const applyTheme = () => {
      const dark = document.documentElement.classList.contains("dark");
      ws.setOptions({
        waveColor: color ?? (dark ? "#3d4450" : "#c9d2de"),
        progressColor: progressColor ?? (dark ? "#7792ff" : "#5374f5"),
        cursorColor: dark ? "#a4b0c1" : "#66758b",
      });
    };
    const mo = new MutationObserver(applyTheme);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });

    return () => {
      mo.disconnect();
      ws.destroy();
      wsRef.current = null;
      regionsRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [url, waveform]);

  /* 外部受控 region 同步（按值比较，避免拖拽回调循环） */
  useEffect(() => {
    const regions = regionsRef.current;
    if (!regions || !ready || !selectable) return;
    const existing = regions.getRegions();
    if (!region) {
      if (existing.length > 0) regions.clearRegions();
      return;
    }
    const match = existing.find(
      (r) => Math.abs(r.start - region.start) < 0.02 && Math.abs(r.end - region.end) < 0.02,
    );
    if (match) {
      existing.forEach((r) => {
        if (r !== match) r.remove();
      });
      return;
    }
    regions.clearRegions();
    regions.addRegion({ start: region.start, end: region.end, color: REGION_COLOR, drag: true, resize: true });
  }, [region, ready, selectable]);

  const toggle = () => handleRef.current.toggle();

  return (
    <div className="w-full">
      {label && <div className="mb-1 text-xs font-medium text-ink-2">{label}</div>}
      <div className="flex items-center gap-3">
        {!compact && (
          <button
            onClick={toggle}
            className="flex h-9 w-9 shrink-0 cursor-pointer items-center justify-center rounded-full bg-brand text-white transition-opacity hover:opacity-90"
            title={playing ? "暂停（Space）" : "播放（Space）"}
            aria-label={playing ? "暂停" : "播放"}
          >
            {playing ? <Pause size={14} fill="currentColor" /> : <Play size={14} fill="currentColor" className="ml-0.5" />}
          </button>
        )}
        <div className="min-w-0 flex-1">
          <div ref={containerRef} className="w-full" />
        </div>
        {!compact && (
          <div className="w-24 shrink-0 text-right font-mono text-xs text-ink-3">
            {fmt(time)} / {fmt(duration)}
          </div>
        )}
      </div>
      {loadError && <div className="mt-1 text-xs text-err">音频加载失败（文件可能已被删除或移动）</div>}
      {selectable && region && (
        <div className="mt-1 text-xs text-ink-3">
          选区：{fmt(region.start)} → {fmt(region.end)}（{(region.end - region.start).toFixed(2)}s）
          <button
            className="ml-2 cursor-pointer text-brand hover:underline"
            onClick={() => {
              regionsRef.current?.clearRegions();
              cbRef.current.onRegionChange?.(null);
            }}
          >
            清除
          </button>
        </div>
      )}
    </div>
  );
}