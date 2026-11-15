/**
 * 任务历史：状态/类型过滤 + 8s 轮询运行中任务 + 表格 + 详情弹窗 +
 * 取消/重试/删除/标记接受 + 批量清理失败任务。
 */
import { useState } from "react";
import { Eye, History, RefreshCw, Trash2 } from "lucide-react";
import { api } from "../api";
import type { StudioMode, ViewKey } from "../components/AppShell";
import JobDetail from "../components/jobs/JobDetail";
import { ProviderBadge } from "../components/models/ProviderBadge";
import { jobKind, kindLabel, modelLabel, statusTone } from "../components/jobs/shared";
import {
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  InlineError,
  PageHeader,
  Select,
  Skeleton,
  StatusBadge,
  Tabs,
  useToast,
} from "../components/ui";
import { usePoll } from "../hooks";
import type { Job } from "../types";
import { RUNNING, STATUS_LABEL, fmtAgo, fmtDur, fmtTime } from "../types";

const STATUS_TABS = [
  { key: "all", label: "全部" },
  { key: "running", label: "运行中" },
  { key: "completed", label: "已完成" },
  { key: "failed", label: "失败" },
  { key: "cancelled", label: "已取消" },
];

export default function Jobs({ onNavigate }: { onNavigate: (v: ViewKey, m?: StudioMode) => void }) {
  const toast = useToast();
  const [statusFilter, setStatusFilter] = useState("all");
  const [kindFilter, setKindFilter] = useState("all");
  const [tick, setTick] = useState(0);
  const [selected, setSelected] = useState<string | null>(null);
  const [confirmCleanup, setConfirmCleanup] = useState(false);
  const [cleaning, setCleaning] = useState(false);

  /* 单状态交给服务端过滤；「运行中」是多状态集合，取回后本地过滤。
     kind 同时本地过滤，兼容尚未支持 kind 参数的旧后端。 */
  const statusParam = statusFilter === "completed" || statusFilter === "failed" || statusFilter === "cancelled" ? statusFilter : undefined;
  const kindParam = kindFilter === "all" ? undefined : kindFilter;
  const { data: jobs, error } = usePoll<Job[]>(
    () => api.jobs(statusParam, kindParam),
    8000,
    true,
    [statusFilter, kindFilter, tick],
  );

  const refresh = () => setTick((t) => t + 1);

  const filtered = (jobs ?? []).filter((j) => {
    if (kindFilter !== "all" && jobKind(j) !== kindFilter) return false;
    if (statusFilter === "running") return RUNNING.includes(j.status);
    if (statusFilter !== "all") return j.status === statusFilter;
    return true;
  });

  const failedJobs = (jobs ?? []).filter((j) => j.status === "failed");
  const loading = jobs === null && !error;

  const doCleanup = async () => {
    setCleaning(true);
    let ok = 0;
    let fail = 0;
    for (const j of failedJobs) {
      try {
        await api.deleteJob(j.id);
        ok += 1;
      } catch {
        fail += 1;
      }
    }
    setCleaning(false);
    setConfirmCleanup(false);
    if (fail > 0) toast("error", `已清理 ${ok} 个失败任务，${fail} 个删除失败`);
    else toast("success", `已清理 ${ok} 个失败任务及其输出文件`);
    refresh();
  };

  return (
    <div>
      <PageHeader
        title="任务历史"
        description="创作、模型安装与校验任务的完整记录；运行中任务每 8 秒自动刷新。"
        actions={
          <>
            <Button
              variant="ghost"
              icon={<Trash2 size={15} aria-hidden />}
              disabled={failedJobs.length === 0}
              onClick={() => setConfirmCleanup(true)}
            >
              清理失败任务{failedJobs.length > 0 ? `（${failedJobs.length}）` : ""}
            </Button>
            <Button icon={<RefreshCw size={15} aria-hidden />} onClick={refresh}>
              刷新
            </Button>
          </>
        }
      />

      {/* 过滤器 */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Tabs items={STATUS_TABS} value={statusFilter} onChange={setStatusFilter} />
        <div className="w-40">
          <Select value={kindFilter} onChange={(e) => setKindFilter(e.target.value)} aria-label="任务类型过滤">
            <option value="all">全部类型</option>
            <option value="infer">创作任务</option>
            <option value="install">模型安装</option>
            <option value="verify">模型校验</option>
          </Select>
        </div>
      </div>

      {error && (
        <div className="mb-4">
          <InlineError onRetry={refresh}>加载任务列表失败：{error}</InlineError>
        </div>
      )}

      <Card padded={false}>
        {loading ? (
          <div className="space-y-3 p-5">
            {[0, 1, 2, 3, 4].map((i) => (
              <Skeleton key={i} className="h-10 w-full" />
            ))}
          </div>
        ) : jobs === null ? (
          <div className="p-5 text-[13px] text-ink-3">任务列表加载失败，请点击上方「重试」。</div>
        ) : filtered.length === 0 ? (
          (jobs ?? []).length === 0 ? (
            <EmptyState
              icon={<History size={26} aria-hidden />}
              title="还没有任务"
              description="上传音频开始编辑，或从文本生成语音；任务进度与结果都会记录在这里。"
              action={
                <Button variant="primary" onClick={() => onNavigate("studio")}>
                  去创作
                </Button>
              }
            />
          ) : (
            <EmptyState
              icon={<History size={26} aria-hidden />}
              title="没有匹配的任务"
              description="当前过滤条件下没有任务，试试其他状态或类型。"
              action={
                <Button
                  onClick={() => {
                    setStatusFilter("all");
                    setKindFilter("all");
                  }}
                >
                  清除过滤
                </Button>
              }
            />
          )
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="border-b border-line text-left text-xs text-ink-3">
                  <th className="px-4 py-3 font-medium">时间</th>
                  <th className="px-3 py-3 font-medium">模式</th>
                  <th className="px-3 py-3 font-medium">输入文件</th>
                  <th className="hidden px-3 py-3 font-medium lg:table-cell">模型</th>
                  <th className="px-3 py-3 font-medium">状态</th>
                  <th className="hidden px-3 py-3 font-medium md:table-cell">耗时</th>
                  <th className="hidden px-3 py-3 font-medium lg:table-cell">RTF</th>
                  <th className="px-4 py-3 text-right font-medium">操作</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((j) => (
                  <tr
                    key={j.id}
                    onClick={() => setSelected(j.id)}
                    className="cursor-pointer border-b border-line transition-colors last:border-0 hover:bg-subtle/60"
                  >
                    <td className="whitespace-nowrap px-4 py-3 text-ink-2" title={fmtTime(j.created_at)}>
                      {fmtAgo(j.created_at)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-3 font-medium">{kindLabel(j)}</td>
                    <td className="max-w-[220px] truncate px-3 py-3 text-ink-2" title={j.audio?.original_name ?? undefined}>
                      {j.audio?.original_name ?? "—"}
                    </td>
                    <td className="hidden whitespace-nowrap px-3 py-3 text-ink-2 lg:table-cell">
                      {j.provider_id && j.provider_id !== "local" ? <ProviderBadge providerId={j.provider_id} /> : modelLabel(j.model_variant)}
                    </td>
                    <td className="whitespace-nowrap px-3 py-3">
                      <StatusBadge tone={statusTone(j.status)}>{STATUS_LABEL[j.status]}</StatusBadge>
                    </td>
                    <td className="hidden whitespace-nowrap px-3 py-3 text-ink-2 md:table-cell">{fmtDur(j.elapsed_s)}</td>
                    <td className="hidden whitespace-nowrap px-3 py-3 text-ink-2 lg:table-cell">
                      {j.rtf != null ? j.rtf.toFixed(2) : "—"}
                    </td>
                    <td className="whitespace-nowrap px-4 py-3 text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        icon={<Eye size={14} aria-hidden />}
                        onClick={(e) => {
                          e.stopPropagation();
                          setSelected(j.id);
                        }}
                      >
                        详情
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {jobs && (
        <p className="mt-3 text-xs text-ink-3">
          共 {filtered.length} 条{statusFilter !== "all" || kindFilter !== "all" ? "（已过滤）" : ""} · 点击行查看详情、日志与结果
        </p>
      )}

      {/* 详情弹窗 */}
      {selected && (
        <JobDetail
          key={selected}
          jobId={selected}
          onClose={() => setSelected(null)}
          onChanged={refresh}
          onOpenJob={setSelected}
          onNavigate={onNavigate}
        />
      )}

      {/* 批量清理确认 */}
      <ConfirmDialog
        open={confirmCleanup}
        onClose={() => setConfirmCleanup(false)}
        onConfirm={doCleanup}
        title="清理失败任务"
        confirmLabel={`删除 ${failedJobs.length} 个任务`}
        danger
        loading={cleaning}
      >
        将删除当前列表中的 <b>{failedJobs.length}</b> 个失败任务<b>及其输出文件</b>，不可撤销。
        原始上传音频不受影响。确定清理吗？
      </ConfirmDialog>
    </div>
  );
}