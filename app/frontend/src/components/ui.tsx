/**
 * AuK Studio 原创 UI kit — 02-UI-UX设计规范 §2/§5。
 * 浅色优先、深色可切换；状态语义必须 文字+图标/颜色 双通道；无第三方组件库拷贝。
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type ButtonHTMLAttributes,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from "react";
import {
  AlertTriangle,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleDashed,
  Download,
  Info,
  Loader2,
  X,
  XCircle,
} from "lucide-react";

export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/* ---------------- Button ---------------- */

type ButtonVariant = "primary" | "secondary" | "ghost" | "danger" | "outline";

export function Button({
  variant = "secondary",
  size = "md",
  loading = false,
  icon,
  className,
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: "sm" | "md" | "lg";
  loading?: boolean;
  icon?: ReactNode;
}) {
  const base =
    "inline-flex items-center justify-center gap-1.5 font-medium rounded-btn border transition-colors select-none " +
    "disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer whitespace-nowrap";
  const sizes = {
    sm: "h-8 px-3 text-[13px]",
    md: "h-9 px-4 text-sm",
    lg: "h-11 px-5 text-[15px]",
  };
  const variants: Record<ButtonVariant, string> = {
    primary: "bg-brand text-white border-transparent hover:opacity-90",
    secondary: "bg-surface text-ink border-line hover:bg-subtle",
    ghost: "bg-transparent text-ink-2 border-transparent hover:bg-subtle hover:text-ink",
    danger: "bg-err text-white border-transparent hover:opacity-90",
    outline: "bg-transparent text-brand border-brand/40 hover:bg-brand-tint",
  };
  return (
    <button
      className={cn(base, sizes[size], variants[variant], className)}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <Loader2 size={16} className="animate-spin" aria-hidden /> : icon}
      {children}
    </button>
  );
}

export function IconButton({
  label,
  className,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button
      aria-label={label}
      title={label}
      className={cn(
        "inline-flex h-8 w-8 items-center justify-center rounded-btn text-ink-2 transition-colors",
        "hover:bg-subtle hover:text-ink cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed",
        className,
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

/* ---------------- Card / PageHeader ---------------- */

export function Card({
  title,
  action,
  className,
  children,
  padded = true,
}: {
  title?: ReactNode;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
  padded?: boolean;
}) {
  return (
    <section className={cn("rounded-panel border border-line bg-surface", className)}>
      {(title || action) && (
        <header className="flex items-center justify-between gap-3 border-b border-line px-5 py-3.5">
          <h3 className="text-[15px] font-semibold leading-6">{title}</h3>
          {action}
        </header>
      )}
      <div className={cn(padded && "p-5")}>{children}</div>
    </section>
  );
}

export function PageHeader({
  title,
  description,
  actions,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h1 className="text-[26px] font-semibold leading-8 tracking-tight">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm leading-[22px] text-ink-2">{description}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

export function SectionTitle({ children, hint }: { children: ReactNode; hint?: ReactNode }) {
  return (
    <div className="mb-3 flex items-baseline justify-between gap-2">
      <h2 className="text-base font-semibold leading-6">{children}</h2>
      {hint && <span className="text-xs text-ink-3">{hint}</span>}
    </div>
  );
}

/* ---------------- 状态语义（文字+图标+颜色，不单独依赖颜色） ---------------- */

export type StatusTone = "ready" | "neutral" | "progress" | "warn" | "error" | "unknown";

const TONE_STYLE: Record<StatusTone, string> = {
  ready: "bg-ok-tint text-ok",
  neutral: "bg-subtle text-ink-2",
  progress: "bg-brand-tint text-brand",
  warn: "bg-warn-tint text-warn",
  error: "bg-err-tint text-err",
  unknown: "bg-subtle text-ink-3",
};

export function StatusBadge({
  tone,
  children,
  icon,
  className,
}: {
  tone: StatusTone;
  children: ReactNode;
  icon?: ReactNode;
  className?: string;
}) {
  const defaultIcon: Record<StatusTone, ReactNode> = {
    ready: <CheckCircle2 size={13} aria-hidden />,
    neutral: <CircleDashed size={13} aria-hidden />,
    progress: <Loader2 size={13} className="animate-spin" aria-hidden />,
    warn: <AlertTriangle size={13} aria-hidden />,
    error: <XCircle size={13} aria-hidden />,
    unknown: <Info size={13} aria-hidden />,
  };
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium leading-5",
        TONE_STYLE[tone],
        className,
      )}
    >
      {icon ?? defaultIcon[tone]}
      {children}
    </span>
  );
}

export function Dot({ tone, pulse }: { tone: StatusTone; pulse?: boolean }) {
  const color: Record<StatusTone, string> = {
    ready: "bg-ok",
    neutral: "bg-ink-3",
    progress: "bg-brand",
    warn: "bg-warn",
    error: "bg-err",
    unknown: "bg-ink-3",
  };
  return (
    <span className="relative inline-flex h-2 w-2" aria-hidden>
      {pulse && <span className={cn("absolute inline-flex h-full w-full animate-ping rounded-full opacity-60", color[tone])} />}
      <span className={cn("relative inline-flex h-2 w-2 rounded-full", color[tone])} />
    </span>
  );
}

/* ---------------- 表单 ---------------- */

export function Field({
  label,
  hint,
  error,
  required,
  children,
  className,
}: {
  label?: ReactNode;
  hint?: ReactNode;
  error?: string | null;
  required?: boolean;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={cn("block", className)}>
      {label && (
        <span className="mb-1.5 flex items-center gap-1 text-[13px] font-medium text-ink">
          {label}
          {required && <span className="text-err" aria-hidden>*</span>}
        </span>
      )}
      {children}
      {hint && !error && <span className="mt-1 block text-xs leading-[18px] text-ink-3">{hint}</span>}
      {error && (
        <span className="mt-1 flex items-center gap-1 text-xs leading-[18px] text-err" role="alert">
          <AlertTriangle size={12} aria-hidden /> {error}
        </span>
      )}
    </label>
  );
}

const inputCls =
  "w-full rounded-input border border-line bg-surface px-3 py-2 text-sm text-ink placeholder:text-ink-3 " +
  "transition-colors focus:border-brand focus:outline-none disabled:opacity-50";

export function Input({ className, ...rest }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cn(inputCls, className)} {...rest} />;
}

export function Textarea({ className, ...rest }: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea className={cn(inputCls, "min-h-[84px] resize-y leading-[22px]", className)} {...rest} />;
}

export function Select({ className, children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <span className={cn("relative inline-block w-full", className)}>
      <select className={cn(inputCls, "appearance-none pr-8 cursor-pointer")} {...rest}>
        {children}
      </select>
      <ChevronDown size={15} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-3" aria-hidden />
    </span>
  );
}

export function Switch({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label?: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative inline-flex h-[22px] w-[40px] shrink-0 items-center rounded-full transition-colors cursor-pointer disabled:opacity-50",
        checked ? "bg-brand" : "bg-line",
      )}
    >
      <span
        className={cn(
          "inline-block h-[18px] w-[18px] rounded-full bg-white shadow-sm transition-transform",
          checked ? "translate-x-[20px]" : "translate-x-[2px]",
        )}
      />
    </button>
  );
}

export function Checkbox({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (v: boolean) => void;
  label: ReactNode;
  disabled?: boolean;
}) {
  return (
    <label className={cn("inline-flex cursor-pointer items-center gap-2 text-sm", disabled && "opacity-50 cursor-not-allowed")}>
      <button
        type="button"
        role="checkbox"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={cn(
          "flex h-[18px] w-[18px] items-center justify-center rounded-[5px] border transition-colors cursor-pointer",
          checked ? "border-brand bg-brand text-white" : "border-line bg-surface",
        )}
      >
        {checked && <Check size={13} strokeWidth={3} aria-hidden />}
      </button>
      <span onClick={() => !disabled && onChange(!checked)}>{label}</span>
    </label>
  );
}

/* ---------------- Tabs ---------------- */

export function Tabs({
  items,
  value,
  onChange,
  className,
}: {
  items: { key: string; label: ReactNode; disabled?: boolean; badge?: ReactNode }[];
  value: string;
  onChange: (key: string) => void;
  className?: string;
}) {
  return (
    <div role="tablist" className={cn("flex flex-wrap items-center gap-1 rounded-input bg-subtle p-1", className)}>
      {items.map((it) => (
        <button
          key={it.key}
          role="tab"
          aria-selected={value === it.key}
          disabled={it.disabled}
          onClick={() => onChange(it.key)}
          className={cn(
            "inline-flex items-center gap-1.5 rounded-[7px] px-3.5 py-1.5 text-[13px] font-medium transition-colors cursor-pointer",
            "disabled:opacity-45 disabled:cursor-not-allowed",
            value === it.key ? "bg-surface text-ink shadow-sm" : "text-ink-2 hover:text-ink",
          )}
        >
          {it.label}
          {it.badge}
        </button>
      ))}
    </div>
  );
}

/* ---------------- Dialog ---------------- */

export function Dialog({
  open,
  onClose,
  title,
  children,
  footer,
  width = "max-w-lg",
}: {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
  width?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      prev?.focus?.();
    };
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal="true">
      <div className="absolute inset-0 bg-ink/30 backdrop-blur-[2px]" onClick={onClose} aria-hidden />
      <div
        ref={ref}
        tabIndex={-1}
        className={cn("auk-fade-in relative w-full rounded-panel border border-line bg-surface shadow-xl focus:outline-none", width)}
      >
        <header className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="text-base font-semibold">{title}</h2>
          <IconButton label="关闭" onClick={onClose}>
            <X size={17} />
          </IconButton>
        </header>
        <div className="max-h-[65vh] overflow-y-auto px-5 py-4">{children}</div>
        {footer && <footer className="flex justify-end gap-2 border-t border-line px-5 py-3.5">{footer}</footer>}
      </div>
    </div>
  );
}

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  children,
  confirmLabel = "确认",
  danger = false,
  loading = false,
}: {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: ReactNode;
  children: ReactNode;
  confirmLabel?: string;
  danger?: boolean;
  loading?: boolean;
}) {
  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={title}
      footer={
        <>
          <Button onClick={onClose}>取消</Button>
          <Button variant={danger ? "danger" : "primary"} onClick={onConfirm} loading={loading}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      <div className="text-sm leading-[22px] text-ink-2">{children}</div>
    </Dialog>
  );
}

/* ---------------- Toast ---------------- */

type Toast = { id: number; tone: "success" | "error" | "info"; text: string };
const ToastCtx = createContext<(tone: Toast["tone"], text: string) => void>(() => {});
export const useToast = () => useContext(ToastCtx);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const push = useCallback((tone: Toast["tone"], text: string) => {
    const id = Date.now() + Math.random();
    setToasts((t) => [...t.slice(-3), { id, tone, text }]);
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 4200);
  }, []);
  const icons = {
    success: <CheckCircle2 size={16} className="text-ok" aria-hidden />,
    error: <XCircle size={16} className="text-err" aria-hidden />,
    info: <Info size={16} className="text-brand" aria-hidden />,
  };
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-5 right-5 z-[60] flex w-[340px] flex-col gap-2" aria-live="polite">
        {toasts.map((t) => (
          <div
            key={t.id}
            className="auk-toast-in pointer-events-auto flex items-start gap-2.5 rounded-panel border border-line bg-surface px-4 py-3 shadow-lg"
          >
            {icons[t.tone]}
            <span className="flex-1 text-[13px] leading-5">{t.text}</span>
            <button
              className="text-ink-3 hover:text-ink cursor-pointer"
              onClick={() => setToasts((x) => x.filter((y) => y.id !== t.id))}
              aria-label="关闭提示"
            >
              <X size={14} />
            </button>
          </div>
        ))}
      </div>
    </ToastCtx.Provider>
  );
}

/* ---------------- 反馈 / 空状态 ---------------- */

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-input bg-subtle", className)} aria-hidden />;
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
}: {
  icon?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col items-center justify-center px-6 py-12 text-center", className)}>
      {icon && (
        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-subtle text-ink-3">{icon}</div>
      )}
      <h3 className="text-[15px] font-semibold">{title}</h3>
      {description && <p className="mt-1.5 max-w-sm text-[13px] leading-5 text-ink-2">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

export function InlineError({ children, onRetry }: { children: ReactNode; onRetry?: () => void }) {
  return (
    <div className="flex items-start gap-2 rounded-input border border-err/30 bg-err-tint px-3.5 py-2.5 text-[13px] leading-5 text-err" role="alert">
      <XCircle size={15} className="mt-0.5 shrink-0" aria-hidden />
      <span className="flex-1">{children}</span>
      {onRetry && (
        <button className="shrink-0 font-medium underline cursor-pointer" onClick={onRetry}>
          重试
        </button>
      )}
    </div>
  );
}

export function InlineNote({ tone = "info", children }: { tone?: "info" | "warn"; children: ReactNode }) {
  return (
    <div
      className={cn(
        "flex items-start gap-2 rounded-input px-3.5 py-2.5 text-[13px] leading-5",
        tone === "warn" ? "bg-warn-tint text-warn" : "bg-brand-tint text-brand",
      )}
    >
      {tone === "warn" ? <AlertTriangle size={15} className="mt-0.5 shrink-0" aria-hidden /> : <Info size={15} className="mt-0.5 shrink-0" aria-hidden />}
      <span className="flex-1">{children}</span>
    </div>
  );
}

/* ---------------- 进度 ---------------- */

export function Progress({ value, label }: { value?: number | null; label?: string }) {
  const indeterminate = value == null;
  return (
    <div
      className="h-1.5 w-full overflow-hidden rounded-full bg-subtle"
      role="progressbar"
      aria-valuenow={indeterminate ? undefined : Math.round(value)}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-label={label ?? "进度"}
    >
      {indeterminate ? (
        <div className="auk-indeterminate h-full w-1/3 rounded-full bg-brand" />
      ) : (
        <div className="h-full rounded-full bg-brand transition-[width] duration-300" style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
      )}
    </div>
  );
}

export function Spinner({ size = 18, className }: { size?: number; className?: string }) {
  return <Loader2 size={size} className={cn("animate-spin text-brand", className)} aria-label="加载中" />;
}

/* ---------------- Stepper（安装向导） ---------------- */

export function Stepper({
  steps,
  current,
  done,
}: {
  steps: string[];
  current: number;
  done?: number[];
}) {
  return (
    <ol className="flex flex-wrap items-center gap-y-3" aria-label="安装步骤">
      {steps.map((s, i) => {
        const isDone = done?.includes(i) ?? i < current;
        const isCurrent = i === current;
        return (
          <li key={s} className="flex items-center">
            <span className="flex items-center gap-2">
              <span
                className={cn(
                  "flex h-7 w-7 items-center justify-center rounded-full border text-xs font-semibold",
                  isDone && "border-ok bg-ok text-white",
                  isCurrent && !isDone && "border-brand bg-brand-tint text-brand",
                  !isDone && !isCurrent && "border-line bg-surface text-ink-3",
                )}
                aria-current={isCurrent ? "step" : undefined}
              >
                {isDone ? <Check size={14} strokeWidth={3} aria-hidden /> : i + 1}
              </span>
              <span className={cn("text-[13px]", isCurrent ? "font-semibold text-ink" : "text-ink-2")}>{s}</span>
            </span>
            {i < steps.length - 1 && <span className="mx-3 h-px w-6 bg-line sm:w-10" aria-hidden />}
          </li>
        );
      })}
    </ol>
  );
}

/* ---------------- 杂项 ---------------- */

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-5 min-w-5 items-center justify-center rounded-[5px] border border-line bg-subtle px-1.5 font-mono text-[11px] text-ink-2">
      {children}
    </kbd>
  );
}

export function Tooltip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="group/tt relative inline-flex">
      {children}
      <span
        role="tooltip"
        className="pointer-events-none absolute bottom-full left-1/2 z-40 mb-1.5 -translate-x-1/2 whitespace-nowrap rounded-[7px] bg-ink px-2.5 py-1 text-xs text-surface opacity-0 shadow-lg transition-opacity group-hover/tt:opacity-100"
      >
        {label}
      </span>
    </span>
  );
}

export function CopyButton({ text, label = "复制" }: { text: string; label?: string }) {
  const [ok, setOk] = useState(false);
  const toast = useToast();
  return (
    <Button
      size="sm"
      variant="ghost"
      icon={ok ? <Check size={14} className="text-ok" /> : undefined}
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setOk(true);
          setTimeout(() => setOk(false), 1500);
        } catch {
          toast("error", "复制失败：浏览器不允许访问剪贴板");
        }
      }}
    >
      {ok ? "已复制" : label}
    </Button>
  );
}

export function DownloadLink({ href, filename, children }: { href: string; filename?: string; children?: ReactNode }) {
  return (
    <a
      href={href}
      download={filename}
      className="inline-flex h-8 items-center gap-1.5 rounded-btn border border-line bg-surface px-3 text-[13px] font-medium text-ink transition-colors hover:bg-subtle"
    >
      <Download size={14} aria-hidden />
      {children ?? "下载 WAV"}
    </a>
  );
}

/** 表单草稿持久化（模式切换不丢未提交内容） */
export function useDraft<T>(key: string, initial: T): [T, (v: T | ((p: T) => T)) => void, () => void] {
  const [state, setState] = useState<T>(() => {
    try {
      const raw = localStorage.getItem(`auk-draft:${key}`);
      return raw ? { ...initial, ...JSON.parse(raw) } : initial;
    } catch {
      return initial;
    }
  });
  const set = useCallback(
    (v: T | ((p: T) => T)) => {
      setState((prev) => {
        const next = typeof v === "function" ? (v as (p: T) => T)(prev) : v;
        try {
          localStorage.setItem(`auk-draft:${key}`, JSON.stringify(next));
        } catch {
          /* ignore */
        }
        return next;
      });
    },
    [key],
  );
  const clear = useCallback(() => {
    try {
      localStorage.removeItem(`auk-draft:${key}`);
    } catch {
      /* ignore */
    }
    setState(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return [state, set, clear];
}

/** 可折叠区块（高级参数等） */
export function Collapse({
  title,
  children,
  defaultOpen = false,
  badge,
}: {
  title: ReactNode;
  children: ReactNode;
  defaultOpen?: boolean;
  badge?: ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const id = useId();
  return (
    <div className="rounded-input border border-line">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-2 px-3.5 py-2.5 text-[13px] font-medium cursor-pointer"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        aria-controls={id}
      >
        <span className="flex items-center gap-2">
          {title}
          {badge}
        </span>
        <ChevronDown size={15} className={cn("text-ink-3 transition-transform", open && "rotate-180")} aria-hidden />
      </button>
      {open && (
        <div id={id} className="border-t border-line px-3.5 py-3">
          {children}
        </div>
      )}
    </div>
  );
}