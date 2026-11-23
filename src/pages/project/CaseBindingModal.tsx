import { useMemo, useState } from "react";
import { webuiApi } from "@/api";
import type { UiBindingInfo } from "@/api/webui";
import { useAsync } from "@/hooks/useAsync";
import { Btn, Field, Modal, Tag } from "@/components/ui";

/**
 * 用例-页面绑定的唯一修改入口。
 *
 * 设计要点：绑的是**页面**不是 Page Object。用户只需要回答"这条用例在哪个页面验证"，
 * PO 由「页面 + 标题意图」自动推导——页面是稳定锚点，PO 是会重构的实现。
 * 选完立刻能看到"将使用哪个流程"，避免改完不知道会跑什么。
 */
export function CaseBindingModal({ caseId, caseTitle, module, current, suggestion, onClose, onSaved }: {
  caseId: string;
  caseTitle: string;
  module: string;
  current?: UiBindingInfo;
  suggestion?: { pageId: string; pageName: string; poName: string; kind: string; reason: string };
  onClose: () => void;
  onSaved: () => void;
}) {
  const { data: options } = useAsync(async () => await webuiApi.bindingOptions(), [], null);
  const [pageId, setPageId] = useState(current?.pageId || suggestion?.pageId || "");
  const [poName, setPoName] = useState(current?.poName || suggestion?.poName || "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const groups = useMemo(() => {
    const map = new Map<string, NonNullable<typeof options>["pages"]>();
    for (const p of options?.pages ?? []) {
      const list = map.get(p.domain) ?? [];
      list.push(p);
      map.set(p.domain, list);
    }
    return [...map.entries()];
  }, [options]);

  const picked = (options?.pages ?? []).find((p) => p.pageId === pageId);
  const pos = picked?.pos ?? [];
  // 一页多流程时，必须由人选定一个，否则无法确定要跑什么
  const effectivePo = poName && pos.includes(poName) ? poName : (pos.length === 1 ? pos[0] : "");
  const needPickPo = pos.length > 1 && !effectivePo;
  // 规则认为这条用例是接口/数据校验或人工验证时，绑到 UI 页面会制造"跑通但没验证"的假绿
  const conflict = !!picked && (current?.kind === "api" || current?.kind === "manual" || suggestion?.kind === "api" || suggestion?.kind === "manual");

  const save = async (clear = false) => {
    setBusy(true); setErr("");
    try {
      if (!clear && needPickPo) { setErr("该页面有多个流程，请选定一个"); setBusy(false); return; }
      const r = await webuiApi.writeBindings({
        items: [{ caseId, pageId: clear ? null : pageId, poName: clear ? null : (effectivePo || undefined) }],
        clear,
      });
      if (r.errors?.length) setErr(r.errors[0].error);
      else { onSaved(); onClose(); }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "保存失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open title={`绑定页面 · ${caseId}`} onClose={onClose} width="max-w-xl"
      footer={<>
        <Btn v="ghost" onClick={onClose}>取消</Btn>
        {current?.pageId && <Btn v="ghost" onClick={() => void save(true)} disabled={busy}>解除绑定</Btn>}
        <Btn onClick={() => void save(false)} disabled={busy || !pageId || needPickPo}>{busy ? "保存中…" : "保存并确认"}</Btn>
      </>}>
      <div className="space-y-4">
        <div className="rounded-lg bg-ink-50 p-3">
          <div className="text-[13px] font-medium text-ink-800">{caseTitle}</div>
          <div className="mt-1 flex items-center gap-2 text-[11px] text-ink-500">
            <span>模块 {module || "—"}</span>
            {current?.kindLabel && <Tag t={current.kindLabel} c={current.kind === "ui_po" ? "green" : current.kind === "api" ? "blue" : "amber"} dot={false} />}
            {current?.source === "human"
              ? <span className="text-emerald-600">已人工确认</span>
              : <span className="text-amber-600">当前为规则推断，待确认</span>}
          </div>
        </div>

        <Field label="这条用例在哪个页面验证" hint="选页面即可，自动化流程会按页面自动匹配；页面没有流程时会进入「缺 PO」清单，而不是硬跑一个无关流程">
          <select
            className="h-9 w-full rounded-lg border border-line bg-white pl-3 pr-8 text-[13px] text-ink-700 shadow-sm outline-none focus:border-brand-400 focus:ring-4 focus:ring-brand-500/10"
            value={pageId} onChange={(e) => { setPageId(e.target.value); setPoName(""); }}>
            <option value="">— 未绑定 —</option>
            {groups.map(([domain, list]) => (
              <optgroup key={domain} label={domain || "未分组"}>
                {list.map((p) => (
                  <option key={p.pageId} value={p.pageId}>{p.name} · {p.path}</option>
                ))}
              </optgroup>
            ))}
          </select>
        </Field>

        {picked && (
          <div className="rounded-lg border border-line p-3 text-[12px]">
            <div className="text-ink-600">该页面可用的自动化流程</div>
            {pos.length === 0
              ? <div className="mt-1 text-amber-700">暂无 Page Object，保存后这条用例进入「缺 PO」清单，写好后自动变为可执行。</div>
              : pos.length === 1
                ? <div className="mt-1 flex flex-wrap gap-1.5">
                    <Tag t={pos[0]} c="green" dot={false} />
                  </div>
                : <div className="mt-1.5 space-y-1">
                    <div className="text-[11px] text-ink-500">该页有多个流程，请选定这条用例要走哪一个：</div>
                    {pos.map((p) => (
                      <label key={p} className="flex cursor-pointer items-center gap-2 rounded-md px-1.5 py-1 text-[12px] hover:bg-ink-50">
                        <input type="radio" className="accent-brand-600" name="po" checked={effectivePo === p}
                          onChange={() => setPoName(p)} />
                        <span className={effectivePo === p ? "font-medium text-ink-800" : "text-ink-600"}>{p}</span>
                        {p === suggestion?.poName && <Tag t="建议" c="green" dot={false} />}
                      </label>
                    ))}
                  </div>}
          </div>
        )}

        {conflict && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-[12px] leading-5 text-amber-800">
            规则判断这条用例更像<strong>接口/数据校验</strong>（{suggestion?.reason || current?.reason}）。
            绑到 UI 页面后流程仍会跑通，但<strong>不会验证金额、库存、字段这类页面看不到的东西</strong>，
            通过结果不具备证明力。如果确实要走 UI，请确认断言覆盖了页面可见的结果。
          </div>
        )}

        {!current?.pageId && suggestion?.pageName && (
          <div className="text-[11px] text-ink-500">
            规则建议：{suggestion.pageName}{suggestion.poName ? ` / ${suggestion.poName}` : ""}（{suggestion.kind === "ui_po" ? "可执行" : "需补 PO"}）
          </div>
        )}
        {err && <div className="text-[12px] text-rose-600">{err}</div>}
      </div>
    </Modal>
  );
}
