#!/usr/bin/env python3
"""把 llm-wiki 的 Markdown 课件同步为 AI_Studio 前端课程数据。

源目录：shang-pivot/docs/llm-wiki/course
输出：src/content/llm-wiki-course.json

用法：
  backend/.venv/bin/python scripts/sync_llm_wiki_course.py \
    --source /path/to/shang-pivot/docs/llm-wiki/course
"""
from __future__ import annotations

import argparse
import html
import json
import re
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "src" / "content" / "llm-wiki-course.json"


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    raw = text[4:end].strip()
    meta: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip()] = value.strip()
    return meta, text[end + 4 :].lstrip("\n")


def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    codes: list[str] = []

    def stash(match: re.Match[str]) -> str:
        codes.append(match.group(1))
        return f"\x00C{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", stash, text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a href="\2" target="_blank" rel="noreferrer">\1</a>',
        text,
    )
    for index, code in enumerate(codes):
        text = text.replace(f"\x00C{index}\x00", f"<code>{code}</code>")
    return text


def is_special(line: str) -> bool:
    stripped = line.strip()
    return (
        not stripped
        or stripped.startswith("```")
        or stripped.startswith("|")
        or stripped.startswith("#")
        or stripped.startswith(">")
        or stripped == "---"
        or re.match(r"^[-*]\s+", stripped) is not None
        or re.match(r"^\d+\.\s+", stripped) is not None
    )


def render_table(block: list[str]) -> str:
    rows = []
    for line in block:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        rows.append(cells)
    if len(rows) >= 2 and all(re.fullmatch(r":?-{3,}:?", cell) for cell in rows[1]):
        header, body = rows[0], rows[2:]
    else:
        header, body = rows[0], rows[1:]
    out = ['<div class="course-table"><table><thead><tr>']
    out.extend(f"<th>{inline(cell)}</th>" for cell in header)
    out.append("</tr></thead><tbody>")
    for row in body:
        out.append("<tr>")
        out.extend(f"<td>{inline(cell)}</td>" for cell in row)
        out.append("</tr>")
    out.append("</tbody></table></div>")
    return "".join(out)


def markdown_to_html(body: str) -> str:
    lines = body.splitlines()
    out: list[str] = []
    paragraph: list[str] = []
    index = 0

    def flush_paragraph() -> None:
        if paragraph:
            out.append(f"<p>{inline(' '.join(paragraph))}</p>")
            paragraph.clear()

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            index += 1
            continue

        if stripped.startswith("```"):
            flush_paragraph()
            language = stripped[3:].strip()
            code_lines: list[str] = []
            index += 1
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            index += 1
            code = html.escape("\n".join(code_lines))
            out.append(
                f'<pre><code class="language-{language}">{code}</code></pre>'
                if language
                else f"<pre><code>{code}</code></pre>"
            )
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            flush_paragraph()
            level = len(heading.group(1))
            out.append(f"<h{level}>{inline(heading.group(2).strip())}</h{level}>")
            index += 1
            continue

        if stripped.startswith("|"):
            flush_paragraph()
            block: list[str] = []
            while index < len(lines) and lines[index].strip().startswith("|"):
                block.append(lines[index])
                index += 1
            out.append(render_table(block))
            continue

        if stripped.startswith(">"):
            flush_paragraph()
            quote_lines: list[str] = []
            while index < len(lines) and lines[index].strip().startswith(">"):
                quote_lines.append(lines[index].strip()[1:].strip())
                index += 1
            out.append(f"<blockquote><p>{inline(' '.join(quote_lines))}</p></blockquote>")
            continue

        if stripped == "---":
            flush_paragraph()
            out.append("<hr />")
            index += 1
            continue

        unordered = re.match(r"^[-*]\s+(.*)$", stripped)
        ordered = re.match(r"^\d+\.\s+(.*)$", stripped)
        if unordered or ordered:
            flush_paragraph()
            tag = "ul" if unordered else "ol"
            items: list[str] = []
            pattern = r"^[-*]\s+(.*)$" if unordered else r"^\d+\.\s+(.*)$"
            while index < len(lines):
                current = lines[index]
                match = re.match(pattern, current.strip())
                if match:
                    items.append(match.group(1).strip())
                    index += 1
                elif current.startswith("  ") and current.strip() and items:
                    items[-1] += " " + current.strip()
                    index += 1
                else:
                    break
            out.append(f"<{tag}>" + "".join(f"<li>{inline(item)}</li>" for item in items) + f"</{tag}>")
            continue

        if not is_special(line):
            paragraph.append(stripped)
            index += 1
            continue

        paragraph.append(stripped)
        index += 1

    flush_paragraph()
    return "\n".join(out)


def plain_text(rendered: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", rendered)).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="llm-wiki/course 目录")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    source = Path(args.source).resolve()
    if not source.is_dir():
        raise SystemExit(f"源目录不存在：{source}")

    lessons: list[dict[str, object]] = []
    for path in sorted(source.rglob("*.md")):
        if path.name == "README.md":
            continue
        meta, body = parse_frontmatter(path.read_text(encoding="utf-8"))
        if not meta.get("id") or not meta.get("title"):
            continue
        rendered = markdown_to_html(body)
        # 页面头部已经展示标题，正文不再重复一级标题
        rendered = re.sub(r"^<h1>.*?</h1>\s*", "", rendered, count=1, flags=re.S)
        lessons.append(
            {
                "id": meta["id"],
                "kind": meta.get("kind", "lesson"),
                "chapter": meta.get("chapter", "其他"),
                "title": meta["title"],
                "summary": meta.get("summary", ""),
                "duration": int(meta.get("duration", 10)),
                "level": meta.get("level", "入门"),
                "path": str(path.relative_to(source)),
                "html": rendered,
                "plain": plain_text(rendered),
            }
        )

    def sort_key(item: dict[str, object]) -> tuple[int, int]:
        item_id = str(item["id"])
        prefix = item_id[:1]
        number = int(re.sub(r"\D", "", item_id) or 0)
        return (0 if prefix == "L" else 1, number)

    lessons.sort(key=sort_key)
    payload = {
        "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "source": str(source),
        "totalMinutes": sum(int(item["duration"]) for item in lessons),
        "lessons": lessons,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    lesson_count = sum(1 for item in lessons if item["kind"] == "lesson")
    note_count = sum(1 for item in lessons if item["kind"] == "note")
    print(f"Wrote {output} · {lesson_count} lessons / {note_count} notes / {payload['totalMinutes']} min")


if __name__ == "__main__":
    main()
