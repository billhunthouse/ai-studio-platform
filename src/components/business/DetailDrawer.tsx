import type { ReactNode } from "react";
import { Drawer } from "@/components/ui";

export function DetailDrawer({ open, title, onClose, fields, children, footer, width }: {
  open: boolean;
  title: string;
  onClose: () => void;
  fields?: { label: string; value: ReactNode }[];
  children?: ReactNode;
  footer?: ReactNode;
  width?: string;
}) {
  return (
    <Drawer open={open} title={title} onClose={onClose} footer={footer} width={width}>
      {fields && fields.length > 0 && (
        <dl className="space-y-2.5 text-[12px]">
          {fields.map((f) => (
            <div key={f.label} className="flex justify-between gap-4">
              <dt className="shrink-0 text-ink-500">{f.label}</dt>
              <dd className="break-all text-right font-medium text-ink-800">{f.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {children && <div className="mt-4 border-t border-ink-100 pt-4">{children}</div>}
    </Drawer>
  );
}
