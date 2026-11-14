import { useEffect, useRef, useState } from "react";
import WaveSurfer from "wavesurfer.js";
import { Pause, Play, RotateCcw } from "lucide-react";
import type { Waveform } from "../types";
import { cn } from "./ui";
import {
  claimActive,
  claimActiveIfNone,
  onPauseOthers,
  pauseOthers,
  releaseActive,
  type PlayerHandle,
} from "./studio/playback";

interface Props {
  urlA: string;
  urlB: string;
  labelA?: string;
  labelB?: string;
  waveformA?: Waveform | null;
  waveformB?: Waveform | null;
}

/** A/B 对比播放器：两条波形同步播放，切换只改变音量，位置保持对齐。 */
export default function ABPlayer({ urlA, urlB, labelA = "原始 A", labelB = "生成 B", waveformA, waveformB }: Props) {
  const refA = useRef<HTMLDivElement>(null);
  const refB = useRef<HTMLDivElement>(null);
  const wsA = useRef<WaveSurfer | null>(null);
  const wsB = useRef<WaveSurfer | null>(null);
  const [active, setActive] = useState<"A" | "B">("A");
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [dur, setDur] = useState(0);

  /* 播放互斥 + Space 活动播放器注册 */
  const selfToken = useRef<object>({});
  const handleRef = useRef<PlayerHandle>({
    toggle: () => {
      const a = wsA.current, b = wsB.current;
      if (!a || !b) return;
      if (a.isPlaying() || b.isPlaying()) { a.pause(); b.pause(); }
      else { void a.play().catch(() => {}); void b.play().catch(() => {}); }
    },
    pause: () => { wsA.current?.pause(); wsB.current?.pause(); },
  });
  useEffect(() => {
    claimActiveIfNone(handleRef.current);
    const off = onPauseOthers((src) => {
      if (src !== selfToken.current) {
        wsA.current?.pause();
        wsB.current?.pause();
      }
    });
    return () => {
      off();
      releaseActive(handleRef.current);
    };
  }, []);

  useEffect(() => {
    if (!refA.current || !refB.current) return;
    const isDark = document.documentElement.classList.contains("dark");
    const common = {
      height: 56,
      waveColor: isDark ? "#3d4450" : "#c9d2de",
      progressColor: isDark ? "#7792ff" : "#5374f5",
      cursorColor: isDark ? "#a4b0c1" : "#66758b",
      cursorWidth: 1,
      barWidth: 2,
      barGap: 1,
      barRadius: 2,
      normalize: true,
    };
    const a = WaveSurfer.create({
      ...common, container: refA.current, url: urlA,
      peaks: waveformA ? [waveformA.points.flatMap(([mn, mx]) => [mx, mn])] : undefined,
      duration: waveformA?.duration,
    });
    const b = WaveSurfer.create({
      ...common, container: refB.current, url: urlB,
      progressColor: isDark ? "#39c99a" : "#178b6e",
      peaks: waveformB ? [waveformB.points.flatMap(([mn, mx]) => [mx, mn])] : undefined,
      duration: waveformB?.duration,
    });
    wsA.current = a;
    wsB.current = b;
    b.setVolume(0);

    const sync = (src: WaveSurfer, dst: WaveSurfer) => {
      src.on("timeupdate", (t) => {
        setTime(t);
        if (Math.abs(dst.getCurrentTime() - t) > 0.15) dst.setTime(t);
      });
      src.on("play", () => {
        setPlaying(true);
        claimActive(handleRef.current);
        pauseOthers(selfToken.current);
        if (!dst.isPlaying()) void dst.play().catch(() => {});
      });
      src.on("pause", () => { setPlaying(false); if (dst.isPlaying()) dst.pause(); });
      src.on("finish", () => { setPlaying(false); dst.pause(); });
    };
    sync(a, b);
    sync(b, a);
    a.on("ready", (d) => setDur((prev) => Math.max(prev, d)));
    b.on("ready", (d) => setDur((prev) => Math.max(prev, d)));

    /* 主题切换时为已存在实例重新着色（不重建实例） */
    const applyTheme = () => {
      const dark = document.documentElement.classList.contains("dark");
      const themed = {
        waveColor: dark ? "#3d4450" : "#c9d2de",
        progressColor: dark ? "#7792ff" : "#5374f5",
        cursorColor: dark ? "#a4b0c1" : "#66758b",
      };
      a.setOptions(themed);
      b.setOptions({ ...themed, progressColor: dark ? "#39c99a" : "#178b6e" });
    };
    const mo = new MutationObserver(applyTheme);
    mo.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });

    return () => { mo.disconnect(); a.destroy(); b.destroy(); wsA.current = wsB.current = null; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlA, urlB]);

  useEffect(() => {
    wsA.current?.setVolume(active === "A" ? 1 : 0);
    wsB.current?.setVolume(active === "B" ? 1 : 0);
  }, [active]);

  const togglePlay = () => handleRef.current.toggle();

  const restart = () => {
    wsA.current?.setTime(0);
    wsB.current?.setTime(0);
    setTime(0);
  };

  const fmt = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, "0")}`;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <button
          onClick={togglePlay}
          className="flex h-9 w-9 cursor-pointer items-center justify-center rounded-full bg-brand text-white transition-opacity hover:opacity-90"
          aria-label={playing ? "暂停" : "播放"}
          title={playing ? "暂停（Space）" : "播放（Space）"}
        >
          {playing ? <Pause size={14} fill="currentColor" /> : <Play size={14} fill="currentColor" className="ml-0.5" />}
        </button>
        <button
          onClick={restart}
          className="inline-flex cursor-pointer items-center gap-1 rounded-btn border border-line px-2.5 py-1 text-xs text-ink-2 transition-colors hover:bg-subtle"
        >
          <RotateCcw size={12} aria-hidden /> 回到开头
        </button>
        <div className="flex overflow-hidden rounded-btn border border-line text-xs font-medium" role="group" aria-label="A/B 切换">
          <button
            onClick={() => setActive("A")}
            aria-pressed={active === "A"}
            className={cn("cursor-pointer px-3 py-1 transition-colors", active === "A" ? "bg-brand text-white" : "text-ink-2 hover:bg-subtle")}
          >
            A 原始
          </button>
          <button
            onClick={() => setActive("B")}
            aria-pressed={active === "B"}
            className={cn("cursor-pointer px-3 py-1 transition-colors", active === "B" ? "bg-ok text-white" : "text-ink-2 hover:bg-subtle")}
          >
            B 生成
          </button>
        </div>
        <span className="ml-auto font-mono text-xs text-ink-3">{fmt(time)} / {fmt(dur)}</span>
      </div>
      <div className={cn("rounded-input border p-2 transition-colors", active === "A" ? "border-brand/50 bg-brand-tint" : "border-line")}>
        <div className="mb-1 text-xs text-ink-2">{labelA}{active === "A" && " · 正在监听"}</div>
        <div ref={refA} />
      </div>
      <div className={cn("rounded-input border p-2 transition-colors", active === "B" ? "border-ok/50 bg-ok-tint" : "border-line")}>
        <div className="mb-1 text-xs text-ink-2">{labelB}{active === "B" && " · 正在监听"}</div>
        <div ref={refB} />
      </div>
      <p className="text-xs text-ink-3">A/B 在同一播放位置切换，便于逐句对比音色、情绪与韵律。两条音频时长可能不同。</p>
    </div>
  );
}