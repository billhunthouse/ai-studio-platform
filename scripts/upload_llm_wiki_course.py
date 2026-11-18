#!/usr/bin/env python3
"""把 llm-wiki 课件上传到 AI_Studio 知识库。

前置：
  1. AI_Studio 后端已启动（默认 http://127.0.0.1:8000）
  2. 已安装后端依赖（httpx）

用法：
  backend/.venv/bin/python scripts/upload_llm_wiki_course.py \
    --source /path/to/shang-pivot/docs/llm-wiki/course \
    --email zhangwei@corp.com --password '***'

也可以先登录拿 token，再通过 --token 传入。
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

import httpx

DEFAULT_KB = "LLM-wiki 学习中心"


def strip_frontmatter(text: str) -> str:
    if not text.startswith("---\n"):
        return text
    end = text.find("\n---", 4)
    return text[end + 4 :].lstrip("\n") if end >= 0 else text


def login(api: str, email: str, password: str) -> str:
    response = httpx.post(
        f"{api}/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    token = payload.get("data", {}).get("accessToken")
    if not token:
        raise SystemExit(f"登录失败：{payload}")
    return token


def find_or_create_kb(client: httpx.Client, api: str, project: str, name: str) -> str:
    response = client.get(f"{api}/knowledge")
    response.raise_for_status()
    for kb in response.json().get("data", []):
        if kb.get("name") == name:
            return kb["id"]
    response = client.post(
        f"{api}/knowledge",
        json={
            "name": name,
            "description": "尚品汇 LLM-wiki 课程课件与学习笔记：需求、页面、接口、代码、数据表、知识图谱与实战复盘",
            "embedding": "bge-m3",
        },
    )
    response.raise_for_status()
    return response.json()["data"]["id"]


def existing_docs(client: httpx.Client, api: str, kb_id: str) -> dict[str, str]:
    response = client.get(f"{api}/knowledge/docs", params={"kbId": kb_id})
    response.raise_for_status()
    return {doc["filename"]: doc["id"] for doc in response.json().get("data", [])}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--api", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--project", default="ecommerce")
    parser.add_argument("--kb-name", default=DEFAULT_KB)
    parser.add_argument("--email", default=os.getenv("AI_STUDIO_EMAIL", ""))
    parser.add_argument("--password", default=os.getenv("AI_STUDIO_PASSWORD", ""))
    parser.add_argument("--token", default=os.getenv("AI_STUDIO_TOKEN", ""))
    parser.add_argument("--replace", action="store_true", help="删除同名文档后重新上传")
    args = parser.parse_args()

    source = Path(args.source).resolve()
    if not source.is_dir():
        raise SystemExit(f"源目录不存在：{source}")

    token = args.token
    if not token:
        if not args.email or not args.password:
            raise SystemExit("需要 --token，或 --email/--password")
        token = login(args.api, args.email, args.password)

    headers = {"Authorization": f"Bearer {token}", "X-Project-Id": args.project}
    with httpx.Client(headers=headers, timeout=60) as client:
        kb_id = find_or_create_kb(client, args.api, args.project, args.kb_name)
        existing = existing_docs(client, args.api, kb_id)
        print(f"知识库 {args.kb_name} · {kb_id} · 现有 {len(existing)} 篇")

        uploaded = 0
        skipped = 0
        for path in sorted(source.rglob("*.md")):
            if path.name in existing:
                if not args.replace:
                    skipped += 1
                    continue
                client.delete(f"{args.api}/knowledge/docs/{existing[path.name]}").raise_for_status()

            content = strip_frontmatter(path.read_text(encoding="utf-8"))
            response = client.post(
                f"{args.api}/knowledge/docs",
                data={"kbId": kb_id},
                files={"file": (path.name, content.encode("utf-8"), "text/markdown")},
            )
            response.raise_for_status()
            doc = response.json()["data"]
            uploaded += 1
            print(f"  + {doc['filename']} · {doc['chunks']} chunks")

        print(f"完成：上传 {uploaded} 篇，跳过 {skipped} 篇")


if __name__ == "__main__":
    main()
