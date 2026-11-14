/** 任务日志：运行中 1.5s 轮询 api.jobLogs，等宽字体，自动滚底。终态只拉取一次（长间隔兜底）。 */
import { useEffect, useRef } from "react";
import { api } from "../../api";
import { usePoll } from "../../hooks";
import { InlineError } from "../ui";

export default function JobLog({ jobId, active }: { jobId: string; active: boolean }) {
  const { data, error } = usePoll(
    () => api.jobLogs(jobId, 400),
    active ? 1500 : 60000,
    true,
    [jobId, active],
  );
  const boxRef = useRef<HTMLDivElement>(null);
  const lines = data?.lines ?? [];

  useEffect(() => {
    const el = boxRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines.length]);

  return (
    <div className="space-y-2">
      {error && <InlineError>{error}（自动重试中）</InlineError>}
      <div
        ref={boxRef}
        className="h-48 overflow-y-auto rounded-input border border-line bg-subtle p-3 font-mono text-xs leading-relaxed text-ink-2"
        aria-label="任务日志"
        tabIndex={0}
      >
        {lines.length === 0 && <span className="text-ink-3">暂无日志</span>}
        {lines.map((l, i) => (
          <div key={i} className={l.includes("ERROR") ? "text-err" : undefined}>
            {l}
          </div>
        ))}
        {data?.error && <div className="mt-1 text-err">{data.error}</div>}
      </div>
      <p className="text-[11px] leading-4 text-ink-3">
        {active ? "运行中 · 每 1.5 秒自动刷新" : "任务已结束 · 日志为最终内容"}
      </p>
    </div>
  );
}