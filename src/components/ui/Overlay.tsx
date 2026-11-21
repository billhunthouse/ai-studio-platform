import { createPortal } from "react-dom";
import { useEffect, useRef, type ReactNode } from "react";
import { cx } from "@/lib/cx";
import { Icon } from "./Icon";

function Portal({ children }: { children: ReactNode }) {
  return createPortal(children, document.body);
}

function useDialog<T extends HTMLElement>(open: boolean, onClose: () => void) {
  const ref = useRef<T | null>(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    ref.current?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        closeRef.current();
        return;
      }
      if (e.key !== "Tab" || !ref.current) return;
      const items = Array.from(ref.current.querySelectorAll<HTMLElement>(
        'a[href], button:not([disabled]), textarea:not([disabled]), input:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])',
      )).filter((el) => el.getClientRects().length > 0);
      if (items.length === 0) {
        e.preventDefault();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && (document.activeElement === first || document.activeElement === ref.current)) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      previous?.focus?.();
    };
  }, [open]);
  return ref;
}

function CloseButton({ onClose }: { onClose: () => void }) {
  return (
    <button onClick={onClose} className="grid h-8 w-8 place-items-center rounded-lg text-ink-500 hover:bg-ink-100 hover:text-ink-800" aria-label="关闭">
      <Icon name="close" size={16} />
    </button>
  );
}

/* ---------------- Modal ---------------- */
export function Modal({ open, title, onClose, children, footer, width = "max-w-lg" }: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: string;
}) {
  const ref = useDialog<HTMLDivElement>(open, onClose);
  if (!open) return null;
  return (
    <Portal>
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-950/45 p-6 backdrop-blur-[2px]" onClick={onClose}>
        <div ref={ref} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} className={cx("w-full overflow-hidden rounded-xl border border-line bg-white shadow-modal outline-none", width)} onClick={(e) => e.stopPropagation()}>
          <header className="flex h-14 items-center justify-between border-b border-ink-100 px-5">
            <h3 className="text-[15px] font-semibold text-ink-900">{title}</h3>
            <CloseButton onClose={onClose} />
          </header>
          <div className="max-h-[70vh] overflow-y-auto p-5">{children}</div>
          {footer && <footer className="flex justify-end gap-2 border-t border-ink-100 bg-ink-50/60 px-5 py-3">{footer}</footer>}
        </div>
      </div>
    </Portal>
  );
}

/* ---------------- Drawer ---------------- */
export function Drawer({ open, title, onClose, children, footer, width = "w-[480px]" }: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  width?: string;
}) {
  const ref = useDialog<HTMLElement>(open, onClose);
  if (!open) return null;
  return (
    <Portal>
      <div className="fixed inset-0 z-50 bg-ink-950/45 backdrop-blur-[2px]" onClick={onClose}>
        <aside ref={ref} role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} className={cx("absolute right-0 top-0 flex h-full flex-col border-l border-line bg-white shadow-modal outline-none", width)} onClick={(e) => e.stopPropagation()}>
          <header className="flex h-14 shrink-0 items-center justify-between border-b border-ink-100 px-5">
            <h3 className="text-[15px] font-semibold text-ink-900">{title}</h3>
            <CloseButton onClose={onClose} />
          </header>
          <div className="flex-1 overflow-y-auto p-5">{children}</div>
          {footer && <footer className="flex shrink-0 justify-end gap-2 border-t border-ink-100 bg-ink-50/60 px-5 py-3">{footer}</footer>}
        </aside>
      </div>
    </Portal>
  );
}

/* ---------------- Toast ---------------- */
export function ToastStack({ items }: { items: { id: number; message: string }[] }) {
  return (
    <Portal>
      <div role="status" aria-live="polite" className="pointer-events-none fixed bottom-5 left-5 z-[60] space-y-2">
        {items.map((t) => (
          <div key={t.id} className="max-w-sm rounded-lg border border-white/10 bg-ink-950 px-4 py-3 text-xs text-white shadow-pop">{t.message}</div>
        ))}
      </div>
    </Portal>
  );
}
