/**
 * AuK Studio 全局框架 — 02-UI-UX设计规范 §3.1。
 * 左侧分组导航（224/68px）+ 顶部工具栏（64px）+ 资源状态灯（真实测量值）。
 */
import { useEffect, useRef, useState, type ReactNode } from "react";
import {
  Activity, AudioWaveform, ChevronLeft, ChevronRight, CircleHelp, Cpu, Gauge,
  HardDrive, History, LayoutDashboard, Menu, Mic, Moon, Package, Palette,
  Settings, ShieldCheck, Sparkles, Sun, X,
} from "lucide-react";
import { api } from "../api";
import type { ModelsResponse, SystemInfo } from "../types";
import { usePoll } from "../hooks";
import { cn, Dot, IconButton, StatusBadge, Tooltip } from "./ui";

export type ViewKey =
  | "dashboard" | "studio" | "voices" | "models" | "system"
  | "wizard" | "jobs" | "settings" | "about";

export type StudioMode = "edit" | "tts" | "design" | "timbre" | "emotion";

const NAV: { group: string; items: { key: ViewKey; label: string; icon: ReactNode; studioMode?: StudioMode }[] }[] = [
  {
    group: "工作台",
    items: [
      { key: "dashboard", label: "概览", icon: <LayoutDashboard size={18} /> },
      { key: "studio", label: "语音编辑", icon: <AudioWaveform size={18} />, studioMode: "edit" },
      { key: "studio", label: "文本转语音", icon: <Mic size={18} />, studioMode: "tts" },
      { key: "studio", label: "音色设计", icon: <Sparkles size={18} />, studioMode: "design" },
      { key: "voices", label: "音色库", icon: <Palette size={18} /> },
    ],
  },
  {
    group: "模型与系统",
    items: [
      { key: "models", label: "模型管理", icon: <Package size={18} /> },
      { key: "system", label: "环境检测", icon: <Activity size={18} /> },
      { key: "jobs", label: "任务历史", icon: <History size={18} /> },
      { key: "settings", label: "设置", icon: <Settings size={18} /> },
      { key: "about", label: "关于", icon: <CircleHelp size={18} /> },
    ],
  },
];

const VIEW_TITLE: Record<ViewKey, { title: string; sub: string }> = {
  dashboard: { title: "概览", sub: "本地 AI 语音工作台" },
  studio: { title: "创作工作台", sub: "编辑 · 生成 · 对比 · 导出" },
  voices: { title: "音色库", sub: "本地私有的参考音色" },
  models: { title: "模型管理", sub: "安装 · 校验 · 切换" },
  system: { title: "环境检测", sub: "设备与资源就绪状态" },
  wizard: { title: "安装向导", sub: "检测 → 许可 → 安装 → 验证" },
  jobs: { title: "任务历史", sub: "全部任务与结果" },
  settings: { title: "设置", sub: "偏好与默认参数" },
  about: { title: "关于", sub: "许可与声明" },
};

/** 平台 LOGO：猫耳音波播放图标（影脉科技提供）。源图 docs/assets/logo.png，UI 用 256px 衍生物。 */
export function BrandMark({ size = 28 }: { size?: number }) {
  return (
    <img
      src="/logo.png"
      alt="AuK Studio"
      width={size}
      height={size}
      className="shrink-0 rounded-[24%] border border-line/70 object-cover shadow-sm"
      style={{ width: size, height: size }}
    />
  );
}

function ResourcePopover({ onClose }: { onClose: () => void }) {
  const { data: sys } = usePoll<SystemInfo>(() => api.system(), 5000, true);
  const { data: models } = usePoll<ModelsResponse>(() => api.models(), 8000, true);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const pressure = sys?.memory.pressure_level ?? 0;
  const pressureLabel = pressure >= 4 ? "严重" : pressure >= 2 ? "偏高" : pressure === 1 ? "正常" : "不可用";
  const pressureTone = pressure >= 4 ? "error" : pressure >= 2 ? "warn" : pressure === 1 ? "ready" : "unknown";
  const active = models?.models.find((m) => m.active);

  return (
    <div
      ref={ref}
      className="auk-fade-in absolute right-0 top-[calc(100%+8px)] z-40 w-[300px] rounded-panel border border-line bg-surface p-4 shadow-xl"
      role="dialog"
      aria-label="资源状态"
    >
      <div className="mb-3 flex items-center justify-between">
        <span className="text-[13px] font-semibold">资源状态</span>
        <span className="text-[11px] text-ink-3">实时测量 · 每 5s 刷新</span>
      </div>
      <dl className="space-y-2.5 text-[13px]">
        <div className="flex items-center justify-between">
          <dt className="flex items-center gap-1.5 text-ink-2"><Gauge size={14} /> 内存压力</dt>
          <dd><StatusBadge tone={pressureTone as "ready"}>{pressureLabel}</StatusBadge></dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="flex items-center gap-1.5 text-ink-2"><Cpu size={14} /> 统一内存</dt>
          <dd className="font-medium">{sys ? `${sys.memory.total_gb} GB` : "不可用"}</dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="flex items-center gap-1.5 text-ink-2"><HardDrive size={14} /> 磁盘剩余</dt>
          <dd className="font-medium">{sys ? `${sys.disk.free_gb} GB` : "不可用"}</dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="flex items-center gap-1.5 text-ink-2"><Activity size={14} /> 推理后端</dt>
          <dd className="font-medium">{sys?.inference_backend ?? "不可用"}</dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="flex items-center gap-1.5 text-ink-2"><Package size={14} /> 常驻模型</dt>
          <dd className="font-medium">
            {models ? (active ? `${active.display_name}${models.worker.model_loaded ? " · 已加载" : " · 未加载"}` : "无") : "不可用"}
          </dd>
        </div>
        <div className="flex items-center justify-between">
          <dt className="flex items-center gap-1.5 text-ink-2"><ShieldCheck size={14} /> 工作进程</dt>
          <dd>
            {sys ? (
              <StatusBadge tone={sys.worker.alive ? "ready" : "error"}>{sys.worker.alive ? "运行中" : "离线"}</StatusBadge>
            ) : (
              "不可用"
            )}
          </dd>
        </div>
      </dl>
      <p className="mt-3 border-t border-line pt-2.5 text-[11px] leading-4 text-ink-3">
        Apple 统一内存以压力等级为准，不以空闲 RAM 推断；无可靠采样时不显示 GPU 占用百分比。
      </p>
    </div>
  );
}

export default function AppShell({
  view,
  studioMode,
  onNavigate,
  theme,
  setTheme,
  children,
}: {
  view: ViewKey;
  studioMode: StudioMode;
  onNavigate: (v: ViewKey, mode?: StudioMode) => void;
  theme: string;
  setTheme: (t: string) => void;
  children: ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(() => {
    try {
      return localStorage.getItem("auk-sidebar") === "collapsed";
    } catch {
      return false;
    }
  });
  const [mobileOpen, setMobileOpen] = useState(false);
  const [resOpen, setResOpen] = useState(false);
  const { data: sys } = usePoll<SystemInfo>(() => api.system(), 10000, true);
  const { data: models } = usePoll<ModelsResponse>(() => api.models(), 15000, true);

  useEffect(() => {
    try {
      localStorage.setItem("auk-sidebar", collapsed ? "collapsed" : "expanded");
    } catch {
      /* ignore */
    }
  }, [collapsed]);

  const activeModel = models?.models.find((m) => m.active);
  const workerOk = sys?.worker.alive;
  const pressure = sys?.memory.pressure_level ?? 0;
  const resTone = !sys ? "unknown" : pressure >= 4 || !workerOk ? "error" : pressure >= 2 ? "warn" : "ready";
  const meta = VIEW_TITLE[view];

  const isActive = (key: ViewKey, mode?: StudioMode) =>
    key === view && (key !== "studio" || mode === studioMode);

  const sidebar = (
    <div className="flex h-full flex-col">
      {/* 品牌 */}
      <div className={cn("flex h-16 items-center gap-2.5 border-b border-line px-4", collapsed && "justify-center px-0")}>
        <BrandMark />
        {!collapsed && (
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              <span className="text-[15px] font-semibold tracking-tight">AuK Studio</span>
            </div>
            <span className="block text-[10.5px] leading-3 text-ink-3">Unofficial · Local-first</span>
          </div>
        )}
      </div>

      {/* 导航 */}
      <nav className="flex-1 overflow-y-auto px-3 py-4" aria-label="主导航">
        {NAV.map((g) => (
          <div key={g.group} className="mb-5">
            {!collapsed && (
              <div className="mb-1.5 px-2 text-[11px] font-medium uppercase tracking-wider text-ink-3">{g.group}</div>
            )}
            <ul className="space-y-0.5">
              {g.items.map((it) => {
                const active = isActive(it.key, it.studioMode);
                const btn = (
                  <button
                    onClick={() => {
                      onNavigate(it.key, it.studioMode);
                      setMobileOpen(false);
                    }}
                    aria-current={active ? "page" : undefined}
                    className={cn(
                      "flex w-full items-center gap-2.5 rounded-btn px-2.5 py-2 text-[13.5px] font-medium transition-colors cursor-pointer",
                      collapsed && "justify-center px-0",
                      active ? "bg-brand-tint text-brand" : "text-ink-2 hover:bg-subtle hover:text-ink",
                    )}
                  >
                    <span className="shrink-0">{it.icon}</span>
                    {!collapsed && <span className="truncate">{it.label}</span>}
                  </button>
                );
                return (
                  <li key={it.label}>
                    {collapsed ? <Tooltip label={it.label}>{btn}</Tooltip> : btn}
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {/* 底部状态 */}
      <div className={cn("border-t border-line px-4 py-3", collapsed && "px-0 text-center")}>
        {collapsed ? (
          <Tooltip label={workerOk ? "本地 · MLX 运行中" : "工作进程离线"}>
            <span className="inline-flex items-center gap-1.5 text-[11px] text-ink-3">
              <Dot tone={workerOk ? "ready" : "error"} />
            </span>
          </Tooltip>
        ) : (
          <div className="flex items-center justify-between">
            <span className="flex items-center gap-1.5 text-[11.5px] text-ink-3">
              <Dot tone={workerOk ? "ready" : "error"} />
              本地 · MLX{sys?.worker.model_loaded ? " · 模型常驻" : ""}
            </span>
            <IconButton label="收起导航" onClick={() => setCollapsed(true)} className="h-6 w-6">
              <ChevronLeft size={14} />
            </IconButton>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="flex h-full">
      {/* 桌面侧栏 */}
      <aside
        className={cn(
          "hidden shrink-0 border-r border-line bg-surface transition-[width] duration-200 lg:block",
          collapsed ? "w-[68px]" : "w-[224px]",
        )}
      >
        {sidebar}
      </aside>

      {/* 移动端抽屉 */}
      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-ink/30" onClick={() => setMobileOpen(false)} aria-hidden />
          <aside className="auk-fade-in absolute left-0 top-0 h-full w-[240px] border-r border-line bg-surface">
            <div className="absolute right-2 top-4 z-10">
              <IconButton label="关闭导航" onClick={() => setMobileOpen(false)}>
                <X size={17} />
              </IconButton>
            </div>
            {sidebar}
          </aside>
        </div>
      )}

      {/* 主区域 */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* 顶栏 */}
        <header className="flex h-16 shrink-0 items-center gap-3 border-b border-line bg-surface px-4 sm:px-7">
          <IconButton label="打开导航" className="lg:hidden" onClick={() => setMobileOpen(true)}>
            <Menu size={19} />
          </IconButton>
          {collapsed && (
            <IconButton label="展开导航" className="hidden lg:inline-flex" onClick={() => setCollapsed(false)}>
              <ChevronRight size={17} />
            </IconButton>
          )}
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2 text-[13px] text-ink-3">
              <span className="hidden sm:inline">AuK Studio</span>
              <span className="hidden sm:inline" aria-hidden>/</span>
              <span className="truncate font-medium text-ink">{meta.title}</span>
            </div>
          </div>

          {/* 当前模型 */}
          <button
            onClick={() => onNavigate("models")}
            className="hidden cursor-pointer items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1.5 text-xs font-medium text-ink-2 transition-colors hover:bg-subtle md:inline-flex"
            title="管理模型"
          >
            <Package size={13} aria-hidden />
            {activeModel ? activeModel.display_name : "未选择模型"}
            <StatusBadge tone={activeModel?.state === "ready" ? "ready" : "neutral"} className="ml-0.5 px-1.5 py-0 text-[10.5px]">
              {activeModel?.state === "ready" ? "就绪" : "未就绪"}
            </StatusBadge>
          </button>

          {/* 资源灯 */}
          <div className="relative">
            <button
              onClick={() => setResOpen((o) => !o)}
              aria-expanded={resOpen}
              aria-label="资源状态"
              className={cn(
                "flex cursor-pointer items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors",
                resTone === "ready" && "border-ok/30 bg-ok-tint text-ok",
                resTone === "warn" && "border-warn/30 bg-warn-tint text-warn",
                resTone === "error" && "border-err/30 bg-err-tint text-err",
                resTone === "unknown" && "border-line bg-subtle text-ink-3",
              )}
            >
              <Dot tone={resTone as "ready"} pulse={resTone === "error"} />
              {sys ? `${sys.disk.free_gb} GB 可用` : "资源检测中"}
            </button>
            {resOpen && <ResourcePopover onClose={() => setResOpen(false)} />}
          </div>

          <IconButton label={theme === "dark" ? "切换浅色模式" : "切换深色模式"} onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
            {theme === "dark" ? <Sun size={17} /> : <Moon size={17} />}
          </IconButton>
          <IconButton label="帮助与关于" onClick={() => onNavigate("about")}>
            <CircleHelp size={17} />
          </IconButton>
        </header>

        {/* 内容：工作台占满视口高度（内部滚动），其他页面常规滚动 */}
        <main className={cn("min-h-0 flex-1", view === "studio" ? "overflow-hidden" : "overflow-y-auto")}>
          <div
            className={cn(
              "mx-auto w-full max-w-[1520px] px-4 sm:px-7",
              view === "studio" ? "h-full py-4" : "py-6 sm:py-7",
            )}
          >
            {children}
          </div>
        </main>
      </div>
    </div>
  );
}