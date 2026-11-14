/** 音色卡片：名称/描述/标签/来源/试听/授权记录/操作。 */
import { Archive, ArchiveRestore, Mic, Sparkles, Trash2, Upload } from "lucide-react";
import { api } from "../../api";
import type { Voice } from "../../types";
import { fmtTime } from "../../types";
import { Button, Card, StatusBadge, cn } from "../ui";
import { allowedUseLabel } from "./shared";

export default function VoiceCard({
  voice,
  onUse,
  onArchive,
  onDelete,
}: {
  voice: Voice;
  onUse: (v: Voice) => void;
  onArchive: (v: Voice) => void;
  onDelete: (v: Voice) => void;
}) {
  return (
    <Card className={cn("flex h-full flex-col", voice.archived && "opacity-70")}>
      <div className="flex h-full flex-col gap-3">
        {/* 标题 + 徽章 */}
        <div className="flex items-start justify-between gap-2">
          <h3 className="min-w-0 truncate text-[15px] font-semibold" title={voice.name}>
            {voice.name}
          </h3>
          <div className="flex shrink-0 items-center gap-1.5">
            {voice.source === "generated" ? (
              <StatusBadge tone="progress" icon={<Sparkles size={12} aria-hidden />}>
                生成
              </StatusBadge>
            ) : (
              <StatusBadge tone="neutral" icon={<Upload size={12} aria-hidden />}>
                上传
              </StatusBadge>
            )}
            {voice.archived && <StatusBadge tone="unknown">已归档</StatusBadge>}
          </div>
        </div>

        {voice.description && <p className="line-clamp-2 text-[13px] leading-5 text-ink-2">{voice.description}</p>}

        {voice.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {voice.tags.map((t) => (
              <span key={t} className="rounded-full bg-subtle px-2 py-0.5 text-[11px] leading-4 text-ink-2">
                {t}
              </span>
            ))}
          </div>
        )}

        {/* 试听 */}
        <audio
          controls
          preload="none"
          src={api.audioStreamUrl(voice.audio_id)}
          className="h-9 w-full"
          aria-label={`试听音色 ${voice.name}`}
        />

        {/* 元信息 */}
        <div className="text-xs leading-[18px] text-ink-3">
          创建 {fmtTime(voice.created_at)} · 允许用途：{allowedUseLabel(voice.allowed_use)}
        </div>

        {/* 授权记录 */}
        <div className="rounded-input bg-subtle px-3 py-2.5">
          <div className="mb-1 flex items-center gap-1.5 text-xs font-medium text-ok">
            <Mic size={12} aria-hidden />
            授权记录
          </div>
          <p className="text-[11px] leading-4 text-ink-2">{voice.consent.statement}</p>
          <p className="mt-1 text-[11px] leading-4 text-ink-3">
            {voice.consent.confirmed ? `确认于 ${fmtTime(voice.consent.confirmed_at)}` : "未确认"}
          </p>
        </div>

        {/* 操作 */}
        <div className="mt-auto flex items-center gap-2 pt-1">
          <Button
            size="sm"
            variant="primary"
            className="flex-1"
            disabled={voice.archived}
            onClick={() => onUse(voice)}
            title={voice.archived ? "已归档音色不可用于创作，请先恢复" : "在文本转语音中使用该参考音色"}
          >
            用于创作
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon={voice.archived ? <ArchiveRestore size={14} aria-hidden /> : <Archive size={14} aria-hidden />}
            onClick={() => onArchive(voice)}
          >
            {voice.archived ? "恢复" : "归档"}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="text-err hover:text-err"
            icon={<Trash2 size={14} aria-hidden />}
            onClick={() => onDelete(voice)}
          >
            删除
          </Button>
        </div>
      </div>
    </Card>
  );
}