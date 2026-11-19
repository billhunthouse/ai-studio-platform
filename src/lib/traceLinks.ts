/** 追溯实体详情页地址：type/id 走查询参数，避免复合 ID 里的 / 与 {} 破坏路由匹配。 */
export function traceHref(type: string, id: string, pid: string) {
  return `/project/${pid}/trace/entity?type=${encodeURIComponent(type)}&id=${encodeURIComponent(id)}`;
}
