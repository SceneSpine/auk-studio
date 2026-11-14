import { useEffect, useRef } from "react";
import { api } from "../api";
import { usePoll } from "../hooks";

export default function LogViewer({ jobId, active }: { jobId: string; active: boolean }) {
  const { data, setData } = usePoll(() => api.jobLogs(jobId, 400), 1500, active, [jobId]);
  const boxRef = useRef<HTMLDivElement>(null);
  const lines = data?.lines ?? [];

  /* 任务结束后（active=false）也拉取一次最终日志，保证回看可用 */
  useEffect(() => {
    let alive = true;
    api.jobLogs(jobId, 400)
      .then((d) => { if (alive) setData(d); })
      .catch(() => {});
    return () => { alive = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  useEffect(() => {
    const el = boxRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [lines.length]);

  return (
    <div
      ref={boxRef}
      role="log"
      aria-label="任务日志"
      className="h-44 overflow-y-auto rounded-input border border-line bg-subtle p-3 font-mono text-xs leading-relaxed text-ink-2"
    >
      {lines.length === 0 && <span className="text-ink-3">暂无日志</span>}
      {lines.map((l, i) => (
        <div key={i} className={l.includes("ERROR") ? "text-err" : ""}>{l}</div>
      ))}
      {data?.error && <div className="mt-1 text-err">{data.error}</div>}
    </div>
  );
}