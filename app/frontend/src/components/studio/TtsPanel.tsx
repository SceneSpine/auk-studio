/** 文本转语音面板：朗读文本 + 参考音色（上传 / 音色库 / 无参考引导）。 */
import { useEffect, useRef, useState } from "react";
import { Check, Mic, Sparkles } from "lucide-react";
import { api } from "../../api";
import type { AudioMeta, Voice } from "../../types";
import { fmtDur } from "../../types";
import UploadZone from "../UploadZone";
import type { StudioMode, ViewKey } from "../AppShell";
import { Button, Card, Field, InlineError, InlineNote, Skeleton, Tabs, Textarea, cn } from "../ui";
import { claimActive, onPauseOthers, pauseOthers, releaseActive, type PlayerHandle } from "./playback";
import type { TtsDraft } from "./shared";

/** 音色库试听 <audio>：接入全局播放互斥与 Space 活动播放器 */
function SampleAudio({ src }: { src: string }) {
  const ref = useRef<HTMLAudioElement>(null);
  const token = useRef<object>({});
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const handle: PlayerHandle = {
      toggle: () => {
        if (el.paused) void el.play().catch(() => {});
        else el.pause();
      },
      pause: () => el.pause(),
    };
    const onPlay = () => {
      claimActive(handle);
      pauseOthers(token.current);
    };
    el.addEventListener("play", onPlay);
    const off = onPauseOthers((s) => {
      if (s !== token.current) el.pause();
    });
    return () => {
      el.removeEventListener("play", onPlay);
      off();
      releaseActive(handle);
    };
  }, []);
  return <audio ref={ref} src={src} controls preload="none" className="h-8 w-full" aria-label="音色试听" />;
}

interface Props {
  draft: TtsDraft;
  onChange: (v: TtsDraft | ((p: TtsDraft) => TtsDraft)) => void;
  refAudio: AudioMeta | null;
  onRefUploaded: (a: AudioMeta) => void;
  onClearRef: () => void;
  onModeChange: (m: StudioMode) => void;
  onNavigate: (v: ViewKey, m?: StudioMode) => void;
}

export default function TtsPanel({ draft, onChange, refAudio, onRefUploaded, onClearRef, onModeChange, onNavigate }: Props) {
  const [voices, setVoices] = useState<Voice[] | null>(null);
  const [voicesError, setVoicesError] = useState("");
  const [loadingVoices, setLoadingVoices] = useState(false);

  const loadVoices = () => {
    setLoadingVoices(true);
    setVoicesError("");
    api.voices()
      .then((v) => setVoices(v.filter((x) => !x.archived)))
      .catch((e) => setVoicesError((e as Error).message))
      .finally(() => setLoadingVoices(false));
  };
  useEffect(() => {
    loadVoices();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const selectedVoice = voices?.find((v) => v.id === draft.voiceId) ?? null;

  return (
    <Card title="文本转语音">
      <div className="space-y-4">
        <Field label="朗读文本" required hint="零样本合成：文本 + 参考音色。目标时长默认按文本长度估算（不少于源时长）。">
          <Textarea
            rows={4}
            value={draft.text}
            onChange={(e) => onChange((d) => ({ ...d, text: e.target.value }))}
            placeholder="输入要朗读的文本，例如：大家好，欢迎来到今天的节目。"
          />
        </Field>

        <div>
          <div className="mb-1.5 text-[13px] font-medium text-ink">参考音色</div>
          <Tabs
            items={[
              { key: "upload", label: "上传参考音频" },
              { key: "voice", label: "从音色库选择" },
              { key: "none", label: "无参考" },
            ]}
            value={draft.refKind}
            onChange={(k) => onChange((d) => ({ ...d, refKind: k as TtsDraft["refKind"] }))}
          />
        </div>

        {draft.refKind === "upload" && (
          <div className="space-y-2">
            {refAudio ? (
              <div className="flex items-center justify-between gap-3 rounded-input border border-line bg-subtle px-3.5 py-2.5">
                <div className="min-w-0 text-sm">
                  <span className="block truncate font-medium">{refAudio.original_name}</span>
                  <span className="text-xs text-ink-3">{fmtDur(refAudio.duration)} · {refAudio.sample_rate}Hz · 将作为音色参考</span>
                </div>
                <Button size="sm" variant="ghost" onClick={onClearRef}>移除</Button>
              </div>
            ) : (
              <UploadZone compact onUploaded={onRefUploaded} />
            )}
          </div>
        )}

        {draft.refKind === "voice" && (
          <div className="space-y-2">
            {loadingVoices && <Skeleton className="h-24" />}
            {voicesError && <InlineError onRetry={loadVoices}>{voicesError}</InlineError>}
            {!loadingVoices && !voicesError && voices && voices.length === 0 && (
              <InlineNote>
                音色库为空。可以先上传参考音频，或到
                <button className="mx-1 cursor-pointer font-medium underline" onClick={() => onNavigate("voices")}>音色库</button>
                管理已保存的参考音色。
              </InlineNote>
            )}
            {voices && voices.length > 0 && (
              <div className="max-h-64 space-y-2 overflow-y-auto pr-1">
                {voices.map((v) => (
                  <div
                    key={v.id}
                    className={cn(
                      "rounded-input border p-3 transition-colors",
                      draft.voiceId === v.id ? "border-brand bg-brand-tint" : "border-line",
                    )}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <button
                        className="flex min-w-0 flex-1 cursor-pointer items-center gap-2 text-left"
                        onClick={() => onChange((d) => ({ ...d, voiceId: v.id }))}
                      >
                        <span
                          className={cn(
                            "flex h-4 w-4 shrink-0 items-center justify-center rounded-full border",
                            draft.voiceId === v.id ? "border-brand bg-brand text-white" : "border-line",
                          )}
                          aria-hidden
                        >
                          {draft.voiceId === v.id && <Check size={10} strokeWidth={3} />}
                        </span>
                        <span className="min-w-0">
                          <span className="block truncate text-sm font-medium">{v.name}</span>
                          {v.description && <span className="block truncate text-xs text-ink-3">{v.description}</span>}
                        </span>
                      </button>
                      {v.tags.length > 0 && (
                        <span className="hidden shrink-0 text-[11px] text-ink-3 sm:inline">{v.tags.slice(0, 2).join(" · ")}</span>
                      )}
                    </div>
                    {v.audio_id && (
                      <div className="mt-2">
                        <SampleAudio src={api.audioStreamUrl(v.audio_id)} />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
            {selectedVoice && (
              <p className="text-xs text-ink-3">已选择「{selectedVoice.name}」作为参考音色。</p>
            )}
          </div>
        )}

        {draft.refKind === "none" && (
          <InlineNote tone="warn">
            零样本 TTS 需要参考音频或音色库参考。如果想不依赖任何参考、按文字描述生成声音，请改用
            <button className="mx-1 cursor-pointer font-medium underline" onClick={() => onModeChange("design")}>
              <Sparkles size={12} className="mr-0.5 inline" aria-hidden />音色设计
            </button>
            模式。
          </InlineNote>
        )}

        <InlineNote>
          <Mic size={13} className="mr-1 inline" aria-hidden />
          参考音色克隆需授权：请确认你对参考声音拥有合法使用权，仅在本机用于非商业研究/评估用途。
        </InlineNote>
      </div>
    </Card>
  );
}