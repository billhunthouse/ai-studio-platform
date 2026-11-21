"""Java 代码扫描器：把 Spring 控制器与 MyBatis-Plus 实体翻译成追溯实体。

设计取舍（写在这里，避免后来者重新猜）：

1. 只读源码文本，不启动 JVM。解析目标是最稳定的三样东西——注解、类名、字段声明，
   而不是方法体逻辑；
2. 接口粒度 = 一个 Controller 方法（与 001-adapter-spec.md 的"接口级"一致）；
3. 表字段来源 = 实体类字段 + BaseEntity 继承字段，类型按 MyBatis 默认映射表翻译；
4. 接口到表的关联只认两种"硬证据"：
   - Service 类 Javadoc 里显式声明的「关联表：a、b」；
   - Service 注入的 Mapper 字段名（OrderMapper → order）。
   两者都没有就不猜，宁可留空也不制造假关联；
5. 所有写入都是 upsert，不删除人工登记的实体。

用法：
    cd backend
    .venv/bin/python -m scanners.java_scanner \
        --repo /path/to/shang-pivot-master/backend \
        --project ecommerce \
        --database-url postgresql://ai:***@127.0.0.1:55432/ai_test_platform

    # 只看解析结果，不写库
    .venv/bin/python -m scanners.java_scanner --repo ... --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import psycopg

try:  # 字段语义库兜底：实体无 @Schema 时按 DDL 注释/知识字典补说明（重扫不丢）
    from agents.field_glossary import comment_for as glossary_comment_for
except ImportError:  # 独立运行于 backend 之外时降级为空
    def glossary_comment_for(_table: str, _col: str):
        return None

# ---------------------------------------------------------------- 常量映射

MODULE_SERVICE = {
    "shang-commerce": "commerce-service",
    "shang-identity": "identity-service",
    "shang-customerservice": "customer-service",
    "shang-common": "common",
    "shang-gateway": "gateway",
    "shang-admin-web": "admin-web",
}

# Java 类型 → PostgreSQL 类型（MyBatis-Plus 默认映射）
SQL_TYPE = {
    "String": "varchar(255)",
    "Long": "bigint", "long": "bigint",
    "Integer": "int4", "int": "int4",
    "Short": "int2", "short": "int2",
    "BigDecimal": "numeric(18,2)",
    "Boolean": "bool", "boolean": "bool",
    "OffsetDateTime": "timestamptz", "LocalDateTime": "timestamptz", "Instant": "timestamptz",
    "LocalDate": "date", "LocalTime": "time",
    "Double": "float8", "double": "float8",
    "Float": "float4", "float": "float4",
    "byte[]": "bytea",
}
PRIMITIVES = {"long", "int", "short", "boolean", "double", "float"}

ANNOTATION_RE = re.compile(r"@[\w.]+(?:\s*\([^)]*\))?")
FIELD_RE = re.compile(r"^(?:private|protected|public)\s+(?!static\b)(?P<type>.+?)\s+(?P<name>\w+)\s*(?:=[^;]*)?;$")
PACKAGE_RE = re.compile(r"^package\s+([\w.]+);", re.M)


def camel_to_snake(name: str) -> str:
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", name)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    return s.lower()


def sql_type(java_type: str, annotations: list[str]) -> str:
    t = java_type.strip()
    if any("JacksonTypeHandler" in a for a in annotations):
        return "jsonb"
    if t in SQL_TYPE:
        return SQL_TYPE[t]
    if t.startswith(("Map<", "List<", "Set<", "Collection<")):
        return "jsonb"
    if t.endswith("[]"):
        return "bytea" if t == "byte[]" else "jsonb"
    return t.lower()


def annotation_value(annotations: list[str], name: str) -> str | None:
    for a in annotations:
        if not a.startswith("@" + name):
            continue
        m = re.search(r'\(\s*(?:value\s*=\s*)?"([^"]*)"', a)
        if m:
            return m.group(1)
    return None


def attr(annotations: list[str], name: str, key: str) -> str | None:
    """取注解里的具名属性，如 @Operation(summary = "x") → x。"""
    for a in annotations:
        if not a.startswith("@" + name):
            continue
        m = re.search(rf'{key}\s*=\s*"([^"]*)"', a)
        if m:
            return m.group(1)
    return None


def has_annotation(annotations: list[str], name: str) -> bool:
    return any(a.startswith("@" + name) for a in annotations)


def unescape_java_string(s: str) -> str:
    return s.replace('\\"', '"').replace("\\\\", "\\").strip().strip('"')


# ---------------------------------------------------------------- 数据模型

@dataclass
class TableFact:
    schema: str
    name: str
    service: str
    columns: list[dict[str, Any]]
    source_file: str
    entity_class: str
    module: str

    @property
    def id(self) -> str:
        return f"table:shang_mall:{self.schema}:{self.name}"


@dataclass
class ApiFact:
    method: str
    path: str
    summary: str
    description: str
    service: str
    auth: str
    controller_class: str
    controller_method: str
    file_path: str
    module: str
    params: list[dict[str, Any]] = field(default_factory=list)
    response_wrapper: str = ""
    response_type: str = ""
    body_type: str = ""
    body_fields: list[dict[str, Any]] = field(default_factory=list)
    # 响应结构：page=分页(data.records/data.total)｜object=data 直接是对象｜empty=无 data
    response_shape: str = ""
    response_fields: list[dict[str, Any]] = field(default_factory=list)
    mapped_tables: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"api:{self.method}:{self.path}"

    @property
    def code_id(self) -> str:
        return f"{self.controller_class}#{self.controller_method}"


# ---------------------------------------------------------------- 实体解析

def parse_entity(path: Path, repo: Path) -> TableFact | None:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if "@TableName" not in text and "extends BaseEntity" not in text:
        return None

    cls = re.search(r"public\s+(?:abstract\s+)?class\s+(\w+)", text)
    if not cls:
        return None
    entity_class = cls.group(1)

    table_name = camel_to_snake(entity_class)
    default_schema = {"shang-commerce": "commerce", "shang-identity": "identity",
                      "shang-customerservice": "public"}
    module_guess = path.parts[len(repo.parts)] if len(path.parts) > len(repo.parts) else ""
    schema = default_schema.get(module_guess, "public")
    m = re.search(r"@TableName\s*\(([^)]*)\)", text)
    if m:
        body = m.group(1)
        v = re.search(r'value\s*=\s*"((?:[^"\\]|\\.)*)"', body) \
            or re.search(r'^\s*"((?:[^"\\]|\\.)*)"', body)
        if v:
            table_name = unescape_java_string(v.group(1))
        s = re.search(r'schema\s*=\s*"([^"]*)"', body)
        if s:
            schema = s.group(1)

    module = path.parts[len(repo.parts)] if len(path.parts) > len(repo.parts) else ""
    service = MODULE_SERVICE.get(module, f"{module.replace('shang-', '')}-service")

    columns: list[dict[str, Any]] = []
    # 继承 BaseEntity 时补上基类字段（真实存在，不补会导致字段数虚少）
    if "extends BaseEntity" in text:
        columns.extend([
            {"name": "id", "type": "bigint", "nullable": False, "primaryKey": True,
             "comment": "主键（雪花 ID）"},
            {"name": "created_at", "type": "timestamptz", "nullable": True, "primaryKey": False,
             "comment": "创建时间"},
            {"name": "updated_at", "type": "timestamptz", "nullable": True, "primaryKey": False,
             "comment": "更新时间"},
            {"name": "deleted", "type": "bool", "nullable": True, "primaryKey": False,
             "comment": "逻辑删除标记"},
            {"name": "trace_id", "type": "varchar(255)", "nullable": True, "primaryKey": False,
             "comment": "链路追踪 ID"},
        ])

    pending: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith(("//", "*", "/*")):
            continue
        if line.startswith("@"):
            pending.append(line)
            continue
        fm = FIELD_RE.match(line)
        if not fm:
            if line.endswith("{"):
                pending.clear()
            continue
        java_type, name = fm.group("type"), fm.group("name")
        anns, pending = pending, []
        if has_annotation(anns, "TableField") and re.search(r"exist\s*=\s*false", " ".join(anns)):
            continue
        col_name = camel_to_snake(name)
        if any(c["name"] == col_name for c in columns):
            continue
        comment = attr(anns, "Schema", "description") or ""
        if not comment:
            glossed = glossary_comment_for(table_name, col_name)
            if glossed:
                comment = glossed[0]
        columns.append({
            "name": col_name,
            "type": sql_type(java_type, anns),
            "nullable": java_type.strip() not in PRIMITIVES,
            "primaryKey": has_annotation(anns, "TableId"),
            "comment": comment,
        })

    if not columns:
        return None
    # 精确类型以真实业务库为准（Java 实体无长度信息，仅作兜底）；重扫不退化
    try:
        from agents.field_glossary import REAL_DB_DSN, real_column_types
        types = real_column_types(schema, table_name)
        if types:
            for col in columns:
                if col["name"] in types:
                    col["type"] = types[col["name"]]
    except Exception:
        pass  # 真实库不可用时保留 Java 推断类型
    return TableFact(schema=schema, name=table_name, service=service, columns=columns,
                     source_file=str(path.relative_to(repo)), entity_class=entity_class,
                     module=module)


# ---------------------------------------------------------------- 接口解析

CLASS_PREFIX_RE = re.compile(r"@RequestMapping\s*\(\s*(?:value\s*=\s*)?" + r'"([^"]*)"')
# 注解参数整段捕获：@PostMapping({"/a","/b"}) 一个方法挂多个 URL 必须全部展开，
# 否则会漏端点（CustomerAuthController 同时挂了 /api/auth/login 与 /api/auth/phone）。
METHOD_MAPPING_RE = re.compile(
    r"@(?P<verb>Get|Post|Put|Delete|Patch)Mapping\b(?P<args>\s*\((?:[^()]|\([^()]*\))*\))?")
SERVICE_FIELD_RE = re.compile(r"private\s+final\s+(\w+Service)\s+(\w+);")
SERVICE_TABLES_RE = re.compile(r"关联表：([^\n<。；;]+)")


def split_top_level(s: str, sep: str = ",") -> list[str]:
    out, depth, buf = [], 0, []
    for ch in s:
        if ch in "(<[":
            depth += 1
        elif ch in ")>]":
            depth -= 1
        if ch == sep and depth == 0:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        out.append("".join(buf))
    return out


def match_paren(s: str, start: int) -> int:
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "(":
            depth += 1
        elif s[i] == ")":
            depth -= 1
            if depth == 0:
                return i
    return -1


def parse_params(sig: str) -> list[dict[str, Any]]:
    lp = sig.find("(")
    rp = match_paren(sig, lp)
    if lp < 0 or rp < 0:
        return []
    out = []
    for chunk in split_top_level(sig[lp + 1:rp]):
        chunk = chunk.strip()
        if not chunk:
            continue
        anns = ANNOTATION_RE.findall(chunk)
        rest = ANNOTATION_RE.sub("", chunk).strip()
        parts = rest.split()
        if len(parts) < 2:
            continue
        p_type, p_name = " ".join(parts[:-1]), parts[-1]
        if any(k in p_type for k in ("HttpServletRequest", "HttpServletResponse",
                                     "HttpSession", "Authentication", "Principal",
                                     "BindingResult", "Model")):
            continue  # 框架注入的容器对象，不是接口契约的一部分
        where = "query"
        required = "false"
        default = None
        if has_annotation(anns, "PathVariable"):
            where, required = "path", "true"
        elif has_annotation(anns, "RequestBody"):
            where, required = "body", "true"
        elif has_annotation(anns, "RequestHeader"):
            where, required = "header", "true"
        for a in anns:
            if a.startswith("@RequestParam"):
                r = re.search(r"required\s*=\s*(true|false)", a)
                if r:
                    required = r.group(1)
                else:
                    required = "true"
                d = re.search(r'defaultValue\s*=\s*"([^"]*)"', a)
                if d:
                    default = d.group(1)
        out.append({
            "name": p_name,
            "in": where,
            "type": p_type,
            "required": required == "true",
            "default": default,
            "description": attr(anns, "Parameter", "description") or "",
            "example": attr(anns, "Parameter", "example") or "",
        })
    return out


def parse_body_fields(repo: Path, fqcn: str) -> list[dict[str, Any]]:
    """解析请求体 DTO 的字段（支持同文件内的内部类）。"""
    simple = fqcn.split(".")[-1]
    # 先找同名文件，再退化为全仓库搜索——DTO 常写成 Service 的内部静态类
    candidates = list(repo.rglob(f"{simple}.java")) or list(repo.rglob("*.java"))
    for path in candidates:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if f"class {simple}" not in text:
            continue
        start = text.find(f"class {simple}")
        body = text[start:]
        fields: list[dict[str, Any]] = []
        pending: list[str] = []
        for raw in body.splitlines():
            line = raw.strip()
            if line.startswith("@"):
                pending.append(line)
                continue
            m = FIELD_RE.match(line)
            if m:
                anns, pending = pending, []
                fields.append({
                    "name": m.group("name"),
                    "type": m.group("type"),
                    "description": attr(anns, "Schema", "description") or "",
                    "example": attr(anns, "Schema", "example") or "",
                    "required": not re.search(r"requiredMode\s*=\s*RequiredMode\.NOT_REQUIRED",
                                              " ".join(anns)),
                })
            elif line and not line.startswith(("*", "//")):
                if line.endswith("}"):
                    break
                pending.clear()
        return fields
    return []


def load_auth_rules(repo: Path) -> tuple[list[str], list[str]]:
    """从 SecurityConfig 读放行清单与需登录前缀——鉴权同样是可扫描的事实。

    放行清单必须整段扫：`requestMatchers(...).permitAll()` 的调用链里，
    第二个 requestMatchers 往往在第一个 permitAll 之后。
    """
    permit: list[str] = []
    for path in repo.rglob("SecurityConfig.java"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for args in re.findall(r"requestMatchers\s*\(([^()]*)\)\s*\.permitAll\(\)", text):
            if "HttpMethod.OPTIONS" in args:
                continue  # 预检请求的 "/**" 放行不代表业务接口公开
            permit.extend(re.findall(r'"(/[^"]*)"', args))
    return permit, ["/admin/", "/api/"]


def match_permit(path: str, permit: list[str]) -> bool:
    for p in permit:
        if p.endswith("/**"):
            if path.startswith(p[:-3]):
                return True
        elif p == path:
            return True
    return False


MAPPER_FIELD_RE = re.compile(r"private\s+final\s+(\w+Mapper)\s+(\w+);")


def resolve_service_tables(repo: Path, svc_class: str, method: str | None = None) -> list[str]:
    """Service 没有 Javadoc「关联表」时，下钻一层看方法体用了哪些 Mapper。

    这是"注释优先、代码兜底"的两级策略：注释是作者显式声明的意图，
    方法体的 Mapper 调用是编译后的事实，两者都拿不到就不建关联。
    """
    for svc_path in repo.rglob(f"{svc_class}.java"):
        text = svc_path.read_text(encoding="utf-8", errors="ignore")
        m = SERVICE_TABLES_RE.search(text)
        if m:
            return [t.strip().strip("。.") for t in re.split(r"[、,，]", m.group(1))
                    if t.strip().strip("。.")]
        body = text
        if method:
            mm = re.search(rf"\b{re.escape(method)}\s*\([^)]*\)\s*\{{", text)
            if mm:
                lb = text.rfind("{", 0, mm.end())
                depth, i = 0, lb
                while i < len(text):
                    if text[i] == "{":
                        depth += 1
                    elif text[i] == "}":
                        depth -= 1
                        if depth == 0:
                            break
                    i += 1
                body = text[lb: i + 1]
        tables: list[str] = []
        for mapper, var in MAPPER_FIELD_RE.findall(text):
            if re.search(rf"\b{re.escape(var)}\s*\.", body):
                t = camel_to_snake(mapper[: -len("Mapper")])
                if t not in tables:
                    tables.append(t)
        return tables
    return []


def parse_controller(path: Path, repo: Path, permit: list[str]) -> list[ApiFact]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    cls = re.search(r"public\s+class\s+(\w+)", text)
    if not cls:
        return []
    controller = cls.group(1)
    prefix_m = CLASS_PREFIX_RE.search(text)
    prefix = prefix_m.group(1) if prefix_m else ""

    module = path.parts[len(repo.parts)] if len(path.parts) > len(repo.parts) else ""
    service = MODULE_SERVICE.get(module, f"{module.replace('shang-', '')}-service")
    rel_path = str(path.relative_to(repo))

    # 变量名 → 该 Service 声明的关联表（按方法取用，避免整个 Controller 的表全算到一个接口上）
    var_service: dict[str, str] = {var: cls for cls, var in SERVICE_FIELD_RE.findall(text)}
    mapper_var: dict[str, str] = {
        var: camel_to_snake(mapper[: -len("Mapper")])
        for mapper, var in MAPPER_FIELD_RE.findall(text)}

    facts: list[ApiFact] = []
    for mm in METHOD_MAPPING_RE.finditer(text):
        # 注解里的字符串即为候选路径（过滤 consumes/produces 之类的属性值）
        sub_paths = [x for x in re.findall(r'"([^"]*)"', mm.group("args") or "")
                     if x.startswith("/") or x == ""]
        sub = sub_paths[0] if sub_paths else ""
        extra_subs = sub_paths[1:]
        after = text[mm.end():]
        # 方法签名：跳过 @Operation 等注解，找到第一个 public ... ( ... ) {
        sig_m = re.search(r"public\s+(?P<ret>[\w<>,\s\.\[\]]+?)\s+(?P<name>\w+)\s*\(", after)
        if not sig_m:
            continue
        between = after[: sig_m.start()]
        sig_start = mm.end() + sig_m.start()
        rp = match_paren(text, sig_start + sig_m.group(0).index("("))
        if rp < 0:
            continue
        sig = text[sig_start: rp + 1]

        anns = ANNOTATION_RE.findall(between)
        summary = attr(anns, "Operation", "summary") or ""
        description = attr(anns, "Operation", "description") or ""

        full = "/" + "/".join(x.strip("/") for x in (prefix, sub) if x.strip("/"))
        full = re.sub(r"/+", "/", full) or "/"
        if len(full) > 1:
            full = full.rstrip("/")

        params = parse_params(sig)
        body_type = ""
        for p in params:
            if p["in"] == "body":
                body_type = p["type"]

        # 方法体：按 ({) 配对截取，用于判断这次调用真正用了哪些 Service
        lb = text.find("{", rp)
        body = ""
        if lb >= 0:
            depth, i = 0, lb
            while i < len(text):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        break
                i += 1
            body = text[lb: i + 1]
        used_tables: list[str] = []

        def add(tbls: list[str]) -> None:
            for t in tbls:
                if t and t not in used_tables:
                    used_tables.append(t)

        for svc_var, svc_cls in var_service.items():
            calls = re.findall(rf"\b{re.escape(svc_var)}\s*\.\s*(\w+)\s*\(", body)
            if not calls:
                continue
            add(resolve_service_tables(repo, svc_cls, calls[0]) or resolve_service_tables(repo, svc_cls))
        for m_var, tbl in mapper_var.items():
            if re.search(rf"\b{re.escape(m_var)}\s*\.", body):
                add([tbl])

        ret = sig_m.group("ret").strip()
        item = generic_payload(ret)
        resp_shape, resp_fields = parse_response(repo, item)

        auth = "public" if match_permit(full, permit) else (
            "login:admin" if full.startswith("/admin/") else "login:customer")

        facts.append(ApiFact(
            method=mm.group("verb").upper(), path=full, summary=summary, description=description,
            service=service, auth=auth, controller_class=controller,
            controller_method=sig_m.group("name"), file_path=rel_path, module=module,
            params=params, response_wrapper=ret, response_type=item,
            response_shape=resp_shape, response_fields=resp_fields,
            body_type=body_type,
            body_fields=parse_body_fields(repo, body_type) if body_type else [],
            mapped_tables=used_tables,
        ))

        # 同一方法挂多个 URL：复制其余端点，鉴权按各自路径重新判定
        for extra in extra_subs:
            ep = "/" + "/".join(x.strip("/") for x in (prefix, extra) if x.strip("/"))
            ep = re.sub(r"/+", "/", ep) or "/"
            if len(ep) > 1:
                ep = ep.rstrip("/")
            facts.append(replace(
                facts[-1], path=ep,
                auth=("public" if match_permit(ep, permit) else
                      ("login:admin" if ep.startswith("/admin/") else "login:customer"))))
    return facts


# ---------------------------------------------------------------- 主流程


def parse_response(repo: Path, item: str) -> tuple[str, list[dict[str, Any]]]:
    """把 controller 的返回类型翻译成 data 的结构，供用例断言定位字段。

    用例断言要写到 `data.xxx`，因此必须知道 data 是分页还是单对象。
    """
    if not item:
        return "empty", []
    base = item.split("<")[0].strip()
    if base in ("void", "Void", "Object"):
        return "empty", []
    if "Page" in base or base.endswith("List") or base.startswith("List"):
        inner = re.findall(r"<([^<>]+)>", item)
        target = inner[-1].strip() if inner else ""
        return "page", parse_body_fields(repo, target) if target else []
    return "object", parse_body_fields(repo, base)


def generic_payload(ret: str) -> str:
    """Result<PageResult<Order>> → PageResult<Order>，只剥一层包装。"""
    if "<" not in ret:
        return ret.strip()
    inner = ret[ret.index("<") + 1:]
    if inner.endswith(">"):
        inner = inner[:-1]
    return inner.strip()


def git_sha(repo: Path) -> str:
    try:
        return subprocess.run(["git", "-C", str(repo), "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:
        return ""


def scan(repo: Path) -> tuple[list[TableFact], list[ApiFact], str]:
    permit, _ = load_auth_rules(repo)
    tables, apis = [], []
    for path in repo.rglob("*.java"):
        if "/test/" in str(path):
            continue
        if path.parent.name == "entity":
            fact = parse_entity(path, repo)
            if fact:
                tables.append(fact)
        elif path.name.endswith("Controller.java"):
            apis.extend(parse_controller(path, repo, permit))
    return tables, apis, git_sha(repo)


def write_db(dsn: str, project: str, tables: list[TableFact], apis: list[ApiFact],
             sha: str, repo_label: str, actor: str = "U-001") -> dict[str, int]:
    stats = {"tables": 0, "apis": 0, "codeArtifacts": 0, "relations": 0, "scanRun": 0}
    with psycopg.connect(dsn) as conn:
        with conn.cursor() as cur:
            run_id = str(uuid.uuid4())
            cur.execute(
                """INSERT INTO trace_scan_runs
                   (id, project_id, adapter, repo, commit_sha, "trigger", status,
                    extracted_count, proposed_count, confirmed_count, stale_count,
                    started_at, started_by)
                   VALUES (%s,%s,%s,%s,%s,'manual','running',0,0,0,0,now(),%s)""",
                (run_id, project, "JAVA_ANNOTATION", repo_label, sha, actor))

            # 0) 重扫前清掉上一轮的扫描结论（人工登记的 HUMAN/SPEC 关系不动）
            cur.execute(
                """DELETE FROM trace_relations
                   WHERE project_id=%s AND source='CODE_SCAN'""", (project,))
            # 上一轮扫出来、这一轮已经不存在的接口/代码实体（例如解析规则修正后消失的
            # 伪端点 api:POST:/ ）必须一起清掉，否则统计里会留下永远无法解释的孤儿。
            keep_api = [a.id for a in apis]
            cur.execute(
                """DELETE FROM trace_apis
                   WHERE project_id=%s AND source='CODE_SCAN' AND NOT (id = ANY(%s))""",
                (project, keep_api))
            # trace_code_artifacts 没有 source 列，它与接口一一对应，按 api_id 反查即可
            cur.execute(
                """DELETE FROM trace_code_artifacts
                   WHERE project_id=%s AND NOT (api_id = ANY(%s))""",
                (project, keep_api))

            # 1) 数据表（含真实字段）
            table_by_name: dict[str, str] = {}
            for t in tables:
                cur.execute(
                    """INSERT INTO trace_tables
                       (id, project_id, database_name, service, schema_name, name, columns,
                        indexes, primary_key, status, source, ddl_ref)
                       VALUES (%s,%s,'shang_mall',%s,%s,%s,%s::jsonb,'[]'::jsonb,%s,'active',
                               'CODE_SCAN',%s)
                       ON CONFLICT (id) DO UPDATE
                         SET columns = EXCLUDED.columns,
                             service = EXCLUDED.service,
                             source  = 'CODE_SCAN',
                             ddl_ref = EXCLUDED.ddl_ref,
                             updated_at = now()""",
                    (t.id, project, t.service, t.schema, t.name,
                     json.dumps(t.columns, ensure_ascii=False),
                     next((c["name"] for c in t.columns if c["primaryKey"]), None),
                     t.source_file))
                table_by_name[t.name] = t.id
                stats["tables"] += 1

            # 已有表（人工登记的）也纳入名字索引，便于建立关联
            cur.execute("SELECT id, name FROM trace_tables WHERE project_id=%s", (project,))
            for tid, name in cur.fetchall():
                table_by_name.setdefault(name, tid)

            # 2) 接口 + 代码制品
            for a in apis:
                req_schema = {"params": a.params}
                if a.body_fields:
                    req_schema["bodyType"] = a.body_type
                    req_schema["bodyFields"] = a.body_fields
                resp_schema = {"wrapper": a.response_wrapper, "shape": a.response_shape,
                               "itemType": a.response_type}
                if a.response_fields:
                    resp_schema["fields"] = a.response_fields
                cur.execute(
                    """INSERT INTO trace_apis
                       (id, project_id, method, path, summary, service, request_schema,
                        response_schema, auth_requirement, internal_calls, status, source, spec_ref)
                       VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,'active','CODE_SCAN',%s)
                       ON CONFLICT (id) DO UPDATE
                         -- 没有 @Operation 时不要用占位摘要覆盖人工/PRD 登记的说明
                         SET summary = CASE
                               WHEN EXCLUDED.summary = EXCLUDED.method || ' ' || EXCLUDED.path
                               THEN trace_apis.summary ELSE EXCLUDED.summary END,
                             service = EXCLUDED.service,
                             request_schema = EXCLUDED.request_schema,
                             response_schema = EXCLUDED.response_schema,
                             auth_requirement = EXCLUDED.auth_requirement,
                             source = 'CODE_SCAN',
                             spec_ref = EXCLUDED.spec_ref,
                             updated_at = now()""",
                    (a.id, project, a.method, a.path, a.summary or f"{a.method} {a.path}",
                     a.service, json.dumps(req_schema, ensure_ascii=False),
                     json.dumps(resp_schema, ensure_ascii=False), a.auth,
                     a.description, f"{a.file_path}#L0"))
                stats["apis"] += 1

                cur.execute(
                    """INSERT INTO trace_code_artifacts
                       (id, project_id, repo, service, api_id, file_path, entry_point,
                        commit_sha, status)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'active')
                       ON CONFLICT (id) DO UPDATE
                         SET file_path = EXCLUDED.file_path,
                             entry_point = EXCLUDED.entry_point,
                             commit_sha = EXCLUDED.commit_sha,
                             api_id = EXCLUDED.api_id""",
                    (a.code_id, project, repo_label, a.service, a.id,
                     a.file_path, f"{a.controller_class}#{a.controller_method}", sha))
                stats["codeArtifacts"] += 1

                # 接口 → 实现代码
                cur.execute(
                    """INSERT INTO trace_relations
                       (id, project_id, src_type, src_id, rel_type, dst_type, dst_id,
                        source, confidence, status, last_seen_commit, confirmed_at)
                       VALUES (%s,%s,'api',%s,'EXPOSED_BY','code_artifact',%s,
                               'CODE_SCAN',95,'confirmed',%s,now())
                       ON CONFLICT (project_id, src_type, src_id, rel_type, dst_type, dst_id)
                       DO UPDATE SET last_seen_commit = EXCLUDED.last_seen_commit""",
                    (str(uuid.uuid4()), project, a.id, a.code_id, sha))
                stats["relations"] += 1

                # 接口 → 表（仅 Service 显式声明「关联表」时建立）
                for tname in a.mapped_tables:
                    tid = table_by_name.get(tname) or table_by_name.get(tname.rstrip("s"))
                    if not tid:
                        continue
                    cur.execute(
                        """INSERT INTO trace_relations
                           (id, project_id, src_type, src_id, rel_type, dst_type, dst_id,
                            source, confidence, status, last_seen_commit, confirmed_at)
                           VALUES (%s,%s,'api',%s,'READS_WRITES','table',%s,
                                   'CODE_SCAN',85,'confirmed',%s,now())
                           ON CONFLICT (project_id, src_type, src_id, rel_type, dst_type, dst_id)
                           DO NOTHING""",
                        (str(uuid.uuid4()), project, a.id, tid, sha))
                    stats["relations"] += 1

            cur.execute(
                """UPDATE trace_scan_runs
                   SET status='success', extracted_count=%s, confirmed_count=%s,
                       finished_at=now()
                   WHERE id=%s""",
                (stats["apis"] + stats["tables"], stats["relations"], run_id))
            stats["scanRun"] = 1
    return stats


def main() -> None:
    ap = argparse.ArgumentParser(description="Java 注解扫描器")
    ap.add_argument("--repo", required=True, help="Java 后端仓库根目录")
    ap.add_argument("--project", default="ecommerce")
    ap.add_argument("--database-url", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--actor", default="U-001", help="扫描发起人 user id（写审计）")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    tables, apis, sha = scan(repo)
    print(f"实体 {len(tables)} 张表 / 接口 {len(apis)} 个 / commit {sha or '-'}")
    for a in apis[:6]:
        print(f"  {a.method:6} {a.path:48} {a.summary[:24]:24} "
              f"参数{len(a.params)} 表{len(a.mapped_tables)} 鉴权{a.auth}")

    if args.dry_run:
        out = Path("scan_preview.json")
        out.write_text(json.dumps({
            "tables": [{"id": t.id, "columns": t.columns} for t in tables],
            "apis": [{"id": a.id, "method": a.method, "path": a.path, "summary": a.summary,
                      "auth": a.auth, "params": a.params, "body": a.body_fields,
                      "tables": a.mapped_tables, "code": a.code_id} for a in apis],
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已写出 {out.resolve()}")
        return

    if not args.database_url:
        raise SystemExit("缺少 --database-url（或用 --dry-run 只看结果）")
    stats = write_db(args.database_url, args.project, tables, apis, sha, repo.name, args.actor)
    print("写库完成：", stats)


if __name__ == "__main__":
    main()
