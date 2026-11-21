#!/usr/bin/env bash
# 四层验证脚本：编译 / 单测 / 视觉 / 交互提示
# 用法: bash verify.sh [项目根目录]
set -uo pipefail

ROOT="${1:-$(pwd)}"
cd "$ROOT" || exit 1

echo "========================================"
echo " 四层验证 · $(basename "$ROOT")"
echo "========================================"
FAILED=0

# 第 1 层：编译
echo ""
echo "[1/4] 编译检查 (tsc --noEmit)"
if [ -f "package.json" ]; then
  if pnpm exec tsc --noEmit >/tmp/scaffold-tsc.log 2>&1; then
    echo "      ✓ 类型检查通过"
  else
    echo "      ✗ 类型检查失败:"
    tail -15 /tmp/scaffold-tsc.log
    FAILED=1
  fi
else
  echo "      - 非 Node 项目，跳过"
fi

# 第 2 层：单测
echo ""
echo "[2/4] 单元测试 (pnpm test)"
if [ -f "package.json" ]; then
  if pnpm test >/tmp/scaffold-test.log 2>&1; then
    echo "      ✓ 单测通过"
    grep -E "Tests|Test Files" /tmp/scaffold-test.log | tail -2
  else
    echo "      ✗ 单测失败:"
    tail -15 /tmp/scaffold-test.log
    FAILED=1
  fi
else
  echo "      - 非 Node 项目，跳过"
fi

# 第 3 层：视觉回归（需要项目配置 Playwright）
echo ""
echo "[3/4] 视觉回归 (screenshot diff)"
if [ -f "playwright.config.ts" ] || [ -f "playwright.config.js" ]; then
  if npx playwright test >/tmp/scaffold-pw.log 2>&1; then
    echo "      ✓ 视觉回归通过"
  else
    echo "      ! 视觉回归有差异，请检查:"
    tail -10 /tmp/scaffold-pw.log
  fi
else
  echo "      - 未配置 Playwright，跳过（建议补上以实现自动视觉验证）"
fi

# 第 4 层：交互冒烟提示
echo ""
echo "[4/4] 交互冒烟（需手动确认）"
echo "      请逐页检查以下状态:"
echo "      - 空状态: 有解释 + 下一步操作"
echo "      - 加载态: 骨架屏，非整页 spinner"
echo "      - 错误态: 原因 + 重试"
echo "      - 权限态: 缺什么权限、找谁开通"
echo "      - 长文本: 截断 + tooltip"

echo ""
echo "========================================"
if [ "$FAILED" -eq 0 ]; then
  echo " 自动验证通过（交互冒烟需人工确认）"
else
  echo " 存在失败项，请修复后再提交"
  exit 1
fi
