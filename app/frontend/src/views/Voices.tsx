/**
 * 音色库：本地私有的参考音色（非永久训练音色）。
 * 新建需强制授权确认；卡片支持试听/用于创作/归档/删除（二次确认）。
 */
import { useState } from "react";
import { Palette, Plus } from "lucide-react";
import { api } from "../api";
import type { StudioMode, ViewKey } from "../components/AppShell";
import CreateVoiceDialog from "../components/voices/CreateVoiceDialog";
import VoiceCard from "../components/voices/VoiceCard";
import {
  Button,
  ConfirmDialog,
  EmptyState,
  InlineError,
  InlineNote,
  PageHeader,
  Skeleton,
  Switch,
  useToast,
} from "../components/ui";
import { usePoll } from "../hooks";
import type { Voice } from "../types";

export default function Voices({ onNavigate }: { onNavigate: (v: ViewKey, m?: StudioMode) => void }) {
  const toast = useToast();
  const [showArchived, setShowArchived] = useState(false);
  const [tick, setTick] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);
  const [deleting, setDeleting] = useState<Voice | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);

  const { data: voices, error } = usePoll<Voice[]>(
    () => api.voices(showArchived),
    60000,
    true,
    [showArchived, tick],
  );
  const refresh = () => setTick((t) => t + 1);
  const loading = voices === null && !error;

  const useVoice = (v: Voice) => {
    try {
      localStorage.setItem("auk-studio-voice", v.id);
    } catch {
      /* 隐私模式下可能不可写，不阻断跳转 */
    }
    toast("info", `已选择音色「${v.name}」，前往文本转语音`);
    onNavigate("studio", "tts");
  };

  const archiveVoice = async (v: Voice) => {
    try {
      await api.archiveVoice(v.id, !v.archived);
      toast("success", v.archived ? `已恢复音色「${v.name}」` : `已归档音色「${v.name}」`);
      refresh();
    } catch (e) {
      toast("error", `操作失败：${(e as Error).message}`);
    }
  };

  const doDelete = async () => {
    if (!deleting) return;
    setDeleteBusy(true);
    try {
      await api.deleteVoice(deleting.id);
      toast("success", `已删除音色「${deleting.name}」（音频文件保留）`);
      setDeleting(null);
      refresh();
    } catch (e) {
      toast("error", `删除失败：${(e as Error).message}`);
    } finally {
      setDeleteBusy(false);
    }
  };

  return (
    <div>
      <PageHeader
        title="音色库"
        description="本地私有 · 默认不上传 · 仅保存已授权的参考样本"
        actions={
          <Button variant="primary" icon={<Plus size={16} aria-hidden />} onClick={() => setCreateOpen(true)}>
            新建音色
          </Button>
        }
      />

      <div className="mb-5">
        <InlineNote tone="warn">
          音色库保存的是「参考音色」（零样本克隆的参考样本），<b>不是永久训练的音色</b>。克隆他人声音须取得合法授权；
          当前推理链依赖 Qwen2.5-Omni-3B（Qwen Research License），仅限非商业研究/评估用途，商业使用需另行授权。
        </InlineNote>
      </div>

      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <label className="flex cursor-pointer items-center gap-2 text-[13px] text-ink-2">
          <Switch checked={showArchived} onChange={setShowArchived} label="显示已归档" />
          显示已归档
        </label>
        {voices && <span className="text-xs text-ink-3">共 {voices.length} 个音色</span>}
      </div>

      {error && (
        <div className="mb-4">
          <InlineError onRetry={refresh}>加载音色库失败：{error}</InlineError>
        </div>
      )}

      {loading ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((i) => (
            <div key={i} className="space-y-3 rounded-panel border border-line bg-surface p-5">
              <Skeleton className="h-6 w-1/2" />
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ))}
        </div>
      ) : voices === null ? (
        <div className="rounded-panel border border-line bg-surface p-5 text-[13px] text-ink-3">
          音色库加载失败，请点击上方「重试」。
        </div>
      ) : voices.length === 0 ? (
        <EmptyState
          icon={<Palette size={26} aria-hidden />}
          title="还没有音色"
          description="保存一段你拥有合法使用权的参考音频，之后可以在文本转语音中直接引用。所有数据仅保存在本机。"
          action={
            <Button variant="primary" icon={<Plus size={16} aria-hidden />} onClick={() => setCreateOpen(true)}>
              新建音色
            </Button>
          }
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {(voices ?? []).map((v) => (
            <VoiceCard key={v.id} voice={v} onUse={useVoice} onArchive={archiveVoice} onDelete={setDeleting} />
          ))}
        </div>
      )}

      <CreateVoiceDialog open={createOpen} onClose={() => setCreateOpen(false)} onCreated={refresh} />

      <ConfirmDialog
        open={!!deleting}
        onClose={() => setDeleting(null)}
        onConfirm={doDelete}
        title="删除音色"
        confirmLabel="删除音色"
        danger
        loading={deleteBusy}
      >
        将删除音色「{deleting?.name}」的记录与授权信息。<b>不会删除参考音频文件本身</b>（它可能仍被历史任务引用）。
        确定删除吗？
      </ConfirmDialog>
    </div>
  );
}