import { type ButtonHTMLAttributes, type InputHTMLAttributes, type ReactNode, type SelectHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { cx } from "@/lib/cx";
import { Icon } from "./Icon";

/* ---------------- Card ---------------- */
export function Card({ title, extra, children, className }: { title?: string; extra?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={cx("bg-white rounded-card border border-line shadow-card", className)}>
      {title && (
        <header className="flex items-center justify-between gap-3 px-5 h-12 border-b border-ink-100">
          <h3 className="text-[15px] font-semibold tracking-[-0.01em] text-ink-900">{title}</h3>
          {extra}
        </header>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}

/* ---------------- Button ---------------- */
type BtnVariant = "primary" | "secondary" | "ghost" | "danger" | "text";
type BtnSize = "sm" | "md";

export function Btn({
  v = "primary",
  size = "md",
  loading,
  className,
  children,
  disabled,
  ...p
}: ButtonHTMLAttributes<HTMLButtonElement> & { v?: BtnVariant; size?: BtnSize; loading?: boolean }) {
  return (
    <button
      {...p}
      disabled={disabled || loading}
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg font-medium whitespace-nowrap transition-colors",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40 focus-visible:ring-offset-2",
        "disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "h-8 px-3 text-xs" : "h-9 px-3.5 text-[13px]",
        v === "primary" && "bg-brand-500 text-white shadow-sm hover:bg-brand-600 active:bg-brand-700",
        v === "secondary" && "border border-line bg-white text-ink-700 shadow-sm hover:border-brand-300 hover:text-brand-600",
        v === "ghost" && "border border-transparent text-ink-600 hover:bg-ink-100 hover:text-ink-900",
        v === "danger" && "border border-transparent text-rose-600 hover:bg-rose-50",
        v === "text" && "px-2 text-brand-600 hover:bg-brand-50",
        className,
      )}
    >
      {loading && <Icon name="spinner" size={14} className="animate-spin" />}
      {children}
    </button>
  );
}

/* ---------------- Tag ---------------- */
export type Tone = "green" | "red" | "amber" | "blue" | "gray";

const TONE_CLASS: Record<Tone, string> = {
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  red: "bg-rose-50 text-rose-700 ring-rose-200",
  amber: "bg-amber-50 text-amber-700 ring-amber-200",
  blue: "bg-brand-50 text-brand-700 ring-brand-200",
  gray: "bg-ink-100 text-ink-600 ring-ink-200",
};

export const tone = (t: string): Tone =>
  /通过|成功|在线|已发布|已解析|正常|启用|已完成/.test(t)
    ? "green"
    : /失败|P0|离线|异常|驳回|高危/.test(t)
      ? "red"
      : /中|待|P1|警告/.test(t)
        ? "amber"
        : /P2|GET|POST|PUT|DELETE|PATCH/.test(t)
          ? "blue"
          : "gray";

export function Tag({ t, c, dot = true }: { t: string; c?: Tone; dot?: boolean }) {
  return (
    <span className={cx("inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset", TONE_CLASS[c ?? tone(t)])}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80" />}
      {t}
    </span>
  );
}

/* ---------------- Form ---------------- */
export function Input(p: InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...p}
      className={cx(
        "h-9 px-3 rounded-lg border border-line bg-white text-[13px] text-ink-800 shadow-sm outline-none",
        "placeholder:text-ink-400 focus:border-brand-400 focus:ring-4 focus:ring-brand-500/10",
        "disabled:cursor-not-allowed disabled:bg-ink-50 disabled:text-ink-500",
        p.className,
      )}
    />
  );
}

export function Textarea(p: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...p}
      className={cx(
        "px-3 py-2.5 rounded-lg border border-line bg-white text-[13px] text-ink-800 shadow-sm outline-none",
        "placeholder:text-ink-400 focus:border-brand-400 focus:ring-4 focus:ring-brand-500/10",
        "disabled:cursor-not-allowed disabled:bg-ink-50 disabled:text-ink-500",
        p.className,
      )}
    />
  );
}

export function Select({ opts, className, ...p }: SelectHTMLAttributes<HTMLSelectElement> & { opts: string[] }) {
  return (
    <select
      {...p}
      className={cx(
        "h-9 pl-3 pr-8 rounded-lg border border-line bg-white text-[13px] text-ink-700 shadow-sm outline-none",
        "focus:border-brand-400 focus:ring-4 focus:ring-brand-500/10",
        className,
      )}
    >
      {opts.map((o) => <option key={o}>{o}</option>)}
    </select>
  );
}

export function Field({ label, hint, children, className, as = "label" }: { label: string; hint?: string; children: ReactNode; className?: string; as?: "label" | "div" }) {
  const Wrapper = as;
  return (
    <Wrapper className={cx("block text-xs", className)}>
      <span className="mb-1.5 block text-[12px] font-medium text-ink-600">{label}</span>
      {children}
      {hint && <span className="mt-1.5 block text-[11px] leading-5 text-ink-500">{hint}</span>}
    </Wrapper>
  );
}

export function Switch({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label?: string }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={label}
      onClick={() => onChange(!checked)}
      className={cx("relative h-5 w-9 rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500/40 focus-visible:ring-offset-2", checked ? "bg-brand-500" : "bg-ink-300")}
    >
      <span className={cx("absolute top-0.5 h-4 w-4 rounded-full bg-white shadow-sm transition-all", checked ? "left-[18px]" : "left-0.5")} />
    </button>
  );
}

/* ---------------- Stat / Bars / Empty / Progress / Skeleton ---------------- */
export function Stat({ label, value, delta, up = true, hint, icon }: { label: string; value: ReactNode; delta?: string; up?: boolean; hint?: string; icon?: ReactNode }) {
  return (
    <section className="rounded-card border border-line bg-white p-5 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <div className="text-[12px] font-medium text-ink-500">{label}</div>
        {icon && <span className="grid h-8 w-8 place-items-center rounded-lg bg-ink-50 text-ink-500">{icon}</span>}
      </div>
      <div className="mt-3 flex items-baseline gap-2">
        <span className="tabular-nums text-[28px] font-semibold leading-none tracking-[-0.03em] text-ink-900">{value}</span>
        {delta && (
          <span className={cx("inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-[11px] font-medium", up ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700")}>
            {up ? "↑" : "↓"} {delta}
          </span>
        )}
      </div>
      {hint && <div className="mt-2 text-[11px] text-ink-500">{hint}</div>}
    </section>
  );
}

export function Bars({ data, color = "bg-brand-500", labels }: { data: number[]; color?: string; labels?: string[] }) {
  const max = Math.max(...data, 1);
  return (
    <div className="relative flex h-44 items-end gap-2 pt-2">
      <div className="pointer-events-none absolute inset-x-0 top-0 bottom-6 flex flex-col justify-between">
        {[0, 1, 2, 3].map((i) => <div key={i} className="h-px w-full bg-ink-100" />)}
      </div>
      {data.map((v, i) => (
        <div key={i} className="relative flex h-full flex-1 flex-col items-center justify-end gap-2">
          <div
            className={cx("w-full max-w-10 rounded-t-md transition-opacity hover:opacity-80", color)}
            style={{ height: `${Math.max(4, (v / max) * 100)}%` }}
            title={String(v)}
          />
          <span className="text-[10px] font-medium text-ink-500">{labels?.[i] ?? ["一", "二", "三", "四", "五", "六", "日"][i] ?? i + 1}</span>
        </div>
      ))}
    </div>
  );
}

export function Empty({ text = "暂无数据", className, action }: { text?: string; className?: string; action?: ReactNode }) {
  return (
    <div className={cx("flex min-h-60 flex-col items-center justify-center gap-3 px-6 py-10 text-center", className)}>
      <div className="grid h-11 w-11 place-items-center rounded-full border border-dashed border-ink-300 bg-ink-50 text-ink-400">
        <Icon name="inbox" size={20} />
      </div>
      <div className="max-w-sm text-[13px] leading-6 text-ink-500">{text}</div>
      {action}
    </div>
  );
}

export function Progress({ value, className }: { value: number; className?: string }) {
  return (
    <div className={cx("h-1.5 rounded-full bg-ink-100", className)}>
      <div
        className={cx("h-1.5 rounded-full transition-all", value >= 100 ? "bg-emerald-500" : "bg-brand-500")}
        style={{ width: `${Math.max(0, Math.min(100, value))}%` }}
      />
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded-md bg-ink-100", className)} />;
}
