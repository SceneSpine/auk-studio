/**
 * 环境检测 — 总体就绪状态 + 检查项列表（warn/fail 展开 detail+suggestion+重试）
 * + 可折叠技术细节 + 安装向导入口 + 重新检测。真实探针，区分观测值与估计值。
 */
import { useState } from "react";
import { RefreshCw, Wand2 } from "lucide-react";
import { api } from "../api";
import type { StudioMode, ViewKey } from "../components/AppShell";
import { Button, InlineError, PageHeader, Skeleton } from "../components/ui";
import { ReadinessBanner } from "../components/system/common";
import { CheckList } from "../components/system/CheckList";
import { TechDetails } from "../components/system/TechDetails";
import { usePoll } from "../hooks";
import { fmtTime } from "../types";

export default function System({ onNavigate }: { onNavigate: (v: ViewKey, m?: StudioMode) => void }) {
  const [tick, setTick] = useState(0);
  const diag = usePoll(api.diagnostics, 30000, true, [tick]);
  const sys = usePoll(api.system, 60000, true, [tick]);
  const retry = () => setTick((t) => t + 1);
  const refreshing = !diag.data && !diag.error;

  return (
    <div className="space-y-5">
      <PageHeader
        title="环境检测"
        description="真实探针测量设备与资源状态，区分观测值与估计值；风险项提供原因、建议与重试。"
        actions={
          <>
            <Button variant="outline" icon={<Wand2 size={15} />} onClick={() => onNavigate("wizard")}>
              运行安装向导
            </Button>
            <Button variant="primary" icon={<RefreshCw size={15} />} onClick={retry} loading={refreshing}>
              重新检测
            </Button>
          </>
        }
      />

      {diag.error && !diag.data && <InlineError onRetry={retry}>环境检测失败：{diag.error}</InlineError>}
      {diag.error && diag.data && (
        <InlineError onRetry={retry}>最近一次刷新失败，显示上一次结果：{diag.error}</InlineError>
      )}

      {refreshing && (
        <div className="space-y-4">
          <Skeleton className="h-24 w-full rounded-panel" />
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full rounded-panel" />
            ))}
          </div>
        </div>
      )}

      {diag.data && (
        <>
          <ReadinessBanner
            level={diag.data.readiness?.level ?? diag.data.overall}
            reasons={diag.data.readiness?.reasons ?? []}
            generatedAt={`${fmtTime(diag.data.generated_at)} · 每 30s 自动刷新`}
          />
          <section aria-label="检查项">
            <h2 className="mb-3 text-base font-semibold leading-6">检查项</h2>
            <CheckList checks={diag.data.checks} onRetry={retry} />
          </section>
          <TechDetails diag={diag.data} sys={sys.data} />
        </>
      )}
    </div>
  );
}