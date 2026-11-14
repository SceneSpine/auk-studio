/**
 * 设置：外观 / 生成默认 / 隐私与网络 / 存储 / 诊断。
 * 全部通过 api.settings / api.saveSettings 真实读写；主题用 useTheme 即时同步。
 */
import { useEffect, useState } from "react";
import { Activity, Cpu, FolderOpen, HardDrive, Moon, Save, ShieldCheck, Sun } from "lucide-react";
import { api } from "../api";
import {
  Button,
  Card,
  Field,
  InlineError,
  InlineNote,
  Input,
  PageHeader,
  Select,
  Skeleton,
  StatusBadge,
  Switch,
  Tabs,
  useToast,
} from "../components/ui";
import { useTheme } from "../hooks";
import type { Diagnostics, Settings, SystemInfo } from "../types";
import { fmtAgo } from "../types";

const READINESS_META: Record<string, { tone: "ready" | "warn" | "error" | "unknown"; label: string }> = {
  ready: { tone: "ready", label: "就绪" },
  caution: { tone: "warn", label: "需注意" },
  blocked: { tone: "error", label: "受阻" },
  unknown: { tone: "unknown", label: "未知" },
};

export default function Settings({
  onNavigate,
  theme: themeProp,
  setTheme: setThemeProp,
}: {
  onNavigate?: (v: import("../components/AppShell").ViewKey, m?: import("../components/AppShell").StudioMode) => void;
  theme?: string;
  setTheme?: (t: string) => void;
} = {}) {
  const themeHook = useTheme();
  const theme = themeProp ?? themeHook.theme;
  const setTheme = setThemeProp ?? themeHook.setTheme;
  const toast = useToast();

  const [settings, setSettings] = useState<Settings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [sys, setSys] = useState<SystemInfo | null>(null);
  const [sysError, setSysError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  /* 生成默认（草稿，点保存才写入） */
  const [variant, setVariant] = useState("flash");
  const [bits, setBits] = useState("8");
  const [sequential, setSequential] = useState(true);
  const [crossfade, setCrossfade] = useState("30");
  const [idleUnload, setIdleUnload] = useState("900");
  const [savingDefaults, setSavingDefaults] = useState(false);
  const [cfError, setCfError] = useState<string | null>(null);
  const [idleError, setIdleError] = useState<string | null>(null);

  /* 内联环境检测 */
  const [diag, setDiag] = useState<Diagnostics | null>(null);
  const [diagBusy, setDiagBusy] = useState(false);
  const [diagError, setDiagError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setLoadError(null);
    setSysError(null);
    api
      .settings()
      .then((s) => {
        if (!alive) return;
        setSettings(s);
        setVariant(s.default_variant === "base" ? "base" : "flash");
        setBits(s.default_bits === "8" ? "8" : "None");
        setSequential(s.default_sequential === "1");
        setCrossfade(s.crossfade_ms ?? "30");
        setIdleUnload(s.idle_unload_s ?? "900");
      })
      .catch((e) => alive && setLoadError((e as Error).message));
    api
      .system()
      .then((s) => alive && setSys(s))
      .catch((e) => alive && setSysError((e as Error).message));
    return () => {
      alive = false;
    };
  }, [tick]);

  const changeTheme = async (t: string) => {
    setTheme(t);
    try {
      await api.saveSettings({ theme: t });
      toast("success", "主题已保存");
    } catch (e) {
      toast("error", `主题已切换，但保存到后端失败：${(e as Error).message}`);
    }
  };

  const toggleUpdateCheck = async (v: boolean) => {
    const prev = settings;
    setSettings((s) => (s ? { ...s, allow_update_check: v ? "1" : "0" } : s));
    try {
      await api.saveSettings({ allow_update_check: v ? "1" : "0" });
      toast("success", v ? "已允许检查版本更新" : "已关闭版本更新检查");
    } catch (e) {
      setSettings(prev);
      toast("error", `保存失败：${(e as Error).message}`);
    }
  };

  const saveDefaults = async () => {
    const cf = Number(crossfade);
    const idle = Number(idleUnload);
    let ok = true;
    if (!Number.isInteger(cf) || cf < 0 || cf > 2000) {
      setCfError("请输入 0–2000 的整数（毫秒）");
      ok = false;
    } else setCfError(null);
    if (!Number.isInteger(idle) || idle < 0) {
      setIdleError("请输入 ≥0 的整数（秒）");
      ok = false;
    } else setIdleError(null);
    if (!ok) return;
    setSavingDefaults(true);
    try {
      const s = await api.saveSettings({
        default_variant: variant,
        default_bits: bits,
        default_sequential: sequential ? "1" : "0",
        crossfade_ms: String(cf),
        idle_unload_s: String(idle),
      });
      setSettings(s);
      toast("success", "生成默认参数已保存");
    } catch (e) {
      toast("error", `保存失败：${(e as Error).message}`);
    } finally {
      setSavingDefaults(false);
    }
  };

  const runDiag = async () => {
    setDiagBusy(true);
    setDiagError(null);
    try {
      setDiag(await api.diagnostics());
    } catch (e) {
      setDiagError((e as Error).message);
    } finally {
      setDiagBusy(false);
    }
  };

  const loading = settings === null && !loadError;

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="设置" description="偏好与默认参数 · 全部保存在本机，不上传任何配置" />

      {loadError && (
        <div className="mb-4">
          <InlineError onRetry={() => setTick((t) => t + 1)}>加载设置失败：{loadError}</InlineError>
        </div>
      )}

      {loading ? (
        <div className="space-y-5">
          {[0, 1, 2].map((i) => (
            <div key={i} className="space-y-3 rounded-panel border border-line bg-surface p-5">
              <Skeleton className="h-6 w-1/3" />
              <Skeleton className="h-9 w-full" />
              <Skeleton className="h-9 w-2/3" />
            </div>
          ))}
        </div>
      ) : (
        settings && (
          <div className="space-y-5">
            {/* 1. 外观 */}
            <Card title="外观">
              <div className="space-y-4">
                <Field label="主题" hint="立即生效并保存到本机与后端">
                  <Tabs
                    items={[
                      { key: "light", label: <span className="flex items-center gap-1.5"><Sun size={14} aria-hidden /> 浅色</span> },
                      { key: "dark", label: <span className="flex items-center gap-1.5"><Moon size={14} aria-hidden /> 深色</span> },
                    ]}
                    value={theme}
                    onChange={changeTheme}
                  />
                </Field>
                <Field label="语言" hint="更多语言开发中，敬请期待">
                  <Select
                    value={settings.language || "zh-CN"}
                    onChange={async (e) => {
                      try {
                        const s = await api.saveSettings({ language: e.target.value });
                        setSettings(s);
                      } catch (err) {
                        toast("error", `保存失败：${(err as Error).message}`);
                      }
                    }}
                    aria-label="界面语言"
                  >
                    <option value="zh-CN">简体中文</option>
                  </Select>
                </Field>
              </div>
            </Card>

            {/* 2. 生成默认 */}
            <Card
              title="生成默认"
              action={
                <Button size="sm" variant="primary" icon={<Save size={14} aria-hidden />} loading={savingDefaults} onClick={saveDefaults}>
                  保存默认
                </Button>
              }
            >
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field label="默认模型">
                  <Select value={variant} onChange={(e) => setVariant(e.target.value)}>
                    <option value="flash">AuK Flash（快速迭代，推荐）</option>
                    <option value="base">AuK Base（更高质量，较慢）</option>
                  </Select>
                </Field>
                <Field label="默认精度" hint="不提供 4-bit：官方结论中文发音可闻退化">
                  <Select value={bits} onChange={(e) => setBits(e.target.value)}>
                    <option value="8">8-bit（推荐）</option>
                    <option value="None">fp32（更高精度）</option>
                  </Select>
                </Field>
                <Field label="交叉淡化（毫秒）" error={cfError} hint="拼接导出时边界淡化，0–2000">
                  <Input
                    type="number"
                    min={0}
                    max={2000}
                    step={1}
                    value={crossfade}
                    onChange={(e) => setCrossfade(e.target.value)}
                  />
                </Field>
                <Field label="空闲卸载（秒）" error={idleError} hint="模型空闲超过该时长自动卸载；0 = 不卸载">
                  <Input
                    type="number"
                    min={0}
                    step={1}
                    value={idleUnload}
                    onChange={(e) => setIdleUnload(e.target.value)}
                  />
                </Field>
                <div className="sm:col-span-2">
                  <label className="flex cursor-pointer items-center gap-2.5 text-sm">
                    <Switch checked={sequential} onChange={setSequential} label="Sequential 解码" />
                    Sequential 解码
                    <span className="text-xs text-ink-3">更稳定，速度略慢；实测与默认结果一致</span>
                  </label>
                </div>
              </div>
            </Card>

            {/* 3. 隐私与网络 */}
            <Card title="隐私与网络">
              <div className="space-y-4">
                <label className="flex cursor-pointer items-start gap-2.5 text-sm">
                  <span className="mt-0.5">
                    <Switch
                      checked={settings.allow_update_check === "1"}
                      onChange={toggleUpdateCheck}
                      label="允许检查版本更新"
                    />
                  </span>
                  <span>
                    允许检查版本更新
                    <span className="mt-0.5 block text-xs leading-[18px] text-ink-3">
                      默认关闭，不联网检查。开启后仅用于检查是否有新版本，不上传任何数据。
                    </span>
                  </span>
                </label>
                <div className="flex items-start gap-2 rounded-input bg-subtle px-3.5 py-3 text-[13px] leading-5 text-ink-2">
                  <ShieldCheck size={16} className="mt-0.5 shrink-0 text-ok" aria-hidden />
                  <span>
                    本应用<b>不上传音频、遥测或设备指纹</b>；推理完全在本机（MLX / Metal）完成，服务默认仅监听
                    127.0.0.1。模型下载仅在你显式发起安装时访问官方源。
                  </span>
                </div>
              </div>
            </Card>

            {/* 4. 存储 */}
            <Card title="存储">
              <div className="space-y-4">
                {sysError && !sys && (
                  <InlineError onRetry={() => setTick((t) => t + 1)}>读取系统路径失败：{sysError}</InlineError>
                )}
                <dl className="space-y-2.5 text-[13px]">
                  {(
                    [
                      { label: "数据目录", value: sys?.paths.data, env: "AUK_DATA_DIR" },
                      { label: "模型目录", value: sys?.paths.models, env: "AUK_MODELS_DIR" },
                      { label: "日志目录", value: sys?.paths.logs, env: "AUK_LOGS_DIR" },
                    ] as const
                  ).map((p) => (
                    <div key={p.label} className="flex flex-col gap-1 sm:flex-row sm:items-center sm:gap-3">
                      <dt className="flex w-24 shrink-0 items-center gap-1.5 text-ink-3">
                        <FolderOpen size={13} aria-hidden /> {p.label}
                      </dt>
                      <dd className="min-w-0 flex-1 break-all rounded-input bg-subtle px-2.5 py-1.5 font-mono text-xs text-ink-2">
                        {p.value ?? "不可用"}
                      </dd>
                    </div>
                  ))}
                </dl>
                <p className="text-xs leading-[18px] text-ink-3">
                  目录通过环境变量 AUK_DATA_DIR / AUK_MODELS_DIR / AUK_LOGS_DIR 配置，修改后重启服务生效。
                </p>
                <div className="rounded-input border border-line px-3.5 py-3 text-[13px] leading-5 text-ink-2">
                  <div className="mb-1.5 flex items-center gap-1.5 font-medium">
                    <HardDrive size={14} aria-hidden /> 数据保留
                  </div>
                  <ul className="list-disc space-y-1 pl-5 text-xs leading-[18px]">
                    <li>原始上传音频<b>只读保留</b>，生成任务不会覆盖原文件。</li>
                    <li>删除任务会同时删除其输出文件；删除音色不删除音频文件本身。</li>
                    <li>
                      备份：在仓库根目录运行 <code className="rounded bg-subtle px-1.5 py-0.5 font-mono text-[11px]">./scripts/backup.sh</code>
                      （备份配置与任务元数据，不含模型权重）。
                    </li>
                  </ul>
                </div>
              </div>
            </Card>

            {/* 5. 诊断 */}
            <Card title="诊断">
              <div className="space-y-4">
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="flex items-center gap-1.5 text-ink-2">
                    <Cpu size={15} aria-hidden /> 并发数
                  </span>
                  <span className="text-right">
                    <b>1（固定）</b>
                    <span className="block text-xs text-ink-3">单任务串行执行，保护统一内存，避免并发推理导致内存压力</span>
                  </span>
                </div>

                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="text-ink-2">Worker 状态</span>
                  {sys ? (
                    <span className="flex items-center gap-2">
                      <StatusBadge tone={sys.worker.alive ? "ready" : "error"}>
                        {sys.worker.alive ? "运行中" : "离线"}
                      </StatusBadge>
                      <span className="text-xs text-ink-3">
                        {sys.worker.model_loaded
                          ? `${sys.worker.model_variant ?? "模型"} 已常驻`
                          : "模型未加载"}
                        {sys.worker.heartbeat ? ` · 心跳 ${fmtAgo(sys.worker.heartbeat)}` : ""}
                      </span>
                    </span>
                  ) : (
                    <span className="text-xs text-ink-3">不可用</span>
                  )}
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <Button icon={<Activity size={15} aria-hidden />} loading={diagBusy} onClick={runDiag}>
                    环境检测
                  </Button>
                  {onNavigate ? (
                    <Button variant="ghost" size="sm" onClick={() => onNavigate("system")}>
                      查看完整报告 →
                    </Button>
                  ) : (
                    <span className="text-xs text-ink-3">完整报告见左侧导航「环境检测」页面</span>
                  )}
                </div>

                {diagError && <InlineError onRetry={runDiag}>环境检测失败：{diagError}</InlineError>}
                {diag && (
                  <div className="space-y-2.5 rounded-input border border-line p-3.5">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge tone={READINESS_META[diag.readiness.level]?.tone ?? "unknown"}>
                        {READINESS_META[diag.readiness.level]?.label ?? diag.readiness.level}
                      </StatusBadge>
                      <span className="text-xs text-ink-3">
                        检查 {diag.checks.length} 项 · 通过 {diag.checks.filter((c) => c.status === "ok").length} · 警告{" "}
                        {diag.checks.filter((c) => c.status === "warn").length} · 失败{" "}
                        {diag.checks.filter((c) => c.status === "fail").length}
                      </span>
                    </div>
                    {diag.readiness.reasons.length > 0 && (
                      <ul className="list-disc pl-5 text-xs leading-[18px] text-ink-2">
                        {diag.readiness.reasons.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    )}
                    {diag.checks
                      .filter((c) => c.status === "warn" || c.status === "fail")
                      .map((c) => (
                        <div key={c.id} className="rounded-input bg-subtle px-3 py-2 text-xs leading-[18px]">
                          <div className="font-medium">
                            {c.label}：{c.value}
                          </div>
                          {c.suggestion && <div className="mt-0.5 text-ink-3">建议：{c.suggestion}</div>}
                        </div>
                      ))}
                  </div>
                )}
                {!diag && !diagError && (
                  <InlineNote>点击「环境检测」运行真实探针（Metal / 内存压力 / 磁盘 / 依赖），结果区分观测值与估计值。</InlineNote>
                )}
              </div>
            </Card>
          </div>
        )
      )}
    </div>
  );
}