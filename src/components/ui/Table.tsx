import { useState, type ChangeEvent, type ReactNode } from "react";
import { cx } from "@/lib/cx";
import { Empty, Input, Select, Skeleton, Tag, tone } from "./primitives";

/* ---------------- Table ---------------- */
const AUTO_TAG = /^(P\d|.*中|.*通过|.*失败|成功|在线|离线|已.*|待.*|启用|停用|正常|异常|GET|POST|PUT|DELETE|PATCH)$/;

export function Table({
  cols,
  rows,
  actions,
  empty = "暂无数据",
  emptyAction,
  loading = false,
  onRowClick,
}: {
  cols: string[];
  rows: ReactNode[][];
  actions?: (i: number) => ReactNode;
  empty?: string;
  emptyAction?: ReactNode;
  loading?: boolean;
  onRowClick?: (i: number) => void;
}) {
  const columnCount = cols.length + (actions ? 1 : 0);
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-full border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-ink-200 bg-ink-50/80 text-left">
            {cols.map((c) => (
              <th key={c} className="whitespace-nowrap px-3 py-3 text-[12px] font-medium text-ink-500">{c}</th>
            ))}
            {actions && <th className="w-px whitespace-nowrap px-3 py-3 text-right text-[12px] font-medium text-ink-500">操作</th>}
          </tr>
        </thead>
        <tbody>
          {loading && Array.from({ length: 6 }).map((_, i) => (
            <tr key={`skeleton-${i}`} className="border-b border-ink-100">
              {Array.from({ length: columnCount }).map((__, j) => (
                <td key={j} className="px-3 py-4"><Skeleton className={j === 1 ? "h-3.5 w-3/4" : "h-3.5 w-16"} /></td>
              ))}
            </tr>
          ))}
          {!loading && rows.length === 0 && (
            <tr>
              <td colSpan={columnCount} className="px-3 py-2">
                <Empty text={empty} action={emptyAction} />
              </td>
            </tr>
          )}
          {!loading && rows.map((r, i) => (
            <tr
              key={i}
              onClick={onRowClick ? () => onRowClick(i) : undefined}
              className={cx("border-b border-ink-100 last:border-0 transition-colors hover:bg-brand-50/40", onRowClick && "cursor-pointer")}
            >
              {r.map((c, j) => (
                <td key={j} className={cx("whitespace-nowrap px-3 py-3.5 text-ink-700", j === 0 && "font-medium text-ink-800")}>
                  {typeof c === "string" && AUTO_TAG.test(c) ? <Tag t={c} c={tone(c)} /> : c}
                </td>
              ))}
              {actions && (
                <td className="whitespace-nowrap px-3 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                  <div className="inline-flex items-center justify-end gap-1">{actions(i)}</div>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ---------------- Toolbar ---------------- */
export function Toolbar({
  children,
  placeholder = "搜索名称/ID",
  onSearch,
  filters,
  statusOptions = ["全部状态", "进行中", "已完成", "失败"],
  onStatusChange,
}: {
  children?: ReactNode;
  placeholder?: string;
  onSearch?: (v: string) => void;
  filters?: ReactNode;
  statusOptions?: string[];
  onStatusChange?: (v: string) => void;
}) {
  const [q, setQ] = useState("");
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      <Input
        placeholder={placeholder}
        className="w-64"
        value={q}
        onChange={(e) => { setQ(e.target.value); onSearch?.(e.target.value); }}
      />
      {filters ?? <Select opts={statusOptions} onChange={(e: ChangeEvent<HTMLSelectElement>) => onStatusChange?.(e.target.value)} />}
      <div className="min-w-2 flex-1" />
      {children}
    </div>
  );
}
